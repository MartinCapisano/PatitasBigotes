"""Los emails de auth salen despues del commit, o no salen.

`test_email_content.py` parchea `_send_message` y por lo tanto verifica el
*texto* del mail, nunca el *envio*. Eso dejaba sin cubrir el bug que motivo este
refactor: los cuatro sitios de auth mandaban SMTP adentro de la transaccion, asi
que un Gmail caido hacia rollback del registro y el usuario veia un 500.

Estos tests fijan la regla en los cuatro sitios. La sonda es un timeline: el
evento `commit` de la conexion anota `commit` y el `_send_message` parcheado
anota `send`. Si alguien vuelve a poner un `send_*` directo, el `send` aparece
antes del `commit` y el test se pone en rojo -- que es exactamente lo que no
pasaba antes.

El evento va en la conexion y no en la sesion a proposito: `after_commit` de la
sesion tambien se dispara al soltar un SAVEPOINT, y los limites de abuso abren
uno (`anti_abuse_s.py:80`) antes de que se arme el mail. Con esa sonda un envio
hecho adentro de la transaccion pasaba por bueno.
"""
from unittest.mock import patch

from sqlalchemy import event

from backend.tests.factories.http_auth import (
    build_password_reset_request_payload,
    build_register_payload,
)
from backend.tests.http._base import HttpFundamentalsBase
from source.db.models import User


class AuthEmailPostCommitTests(HttpFundamentalsBase):
    def setUp(self) -> None:
        super().setUp()
        self.timeline: list[str] = []

        def _record_commit(_connection) -> None:
            self.timeline.append("commit")

        self._record_commit = _record_commit
        event.listen(self.engine, "commit", _record_commit)

    def tearDown(self) -> None:
        event.remove(self.engine, "commit", self._record_commit)
        super().tearDown()

    def _smtp(self, *, fails: bool = False):
        """Parchea el envio real, el unico punto por donde sale un mail."""

        def _side_effect(_msg) -> None:
            self.timeline.append("send")
            if fails:
                raise RuntimeError("smtp is down")

        return patch("source.services.email_s._send_message", side_effect=_side_effect)

    def _assert_sent_after_commit(self) -> None:
        self.assertIn("send", self.timeline)
        self.assertIn(
            "commit",
            self.timeline[: self.timeline.index("send")],
            msg=f"el mail salio sin un commit previo: {self.timeline}",
        )

    def _get_user(self, email: str) -> User | None:
        db = self._db()
        try:
            return db.query(User).filter(User.email == email).first()
        finally:
            db.close()

    # --- auth_r.py:220 · registro ------------------------------------------

    def test_register_sends_verification_only_after_commit(self) -> None:
        with self._smtp():
            response = self.client.post(
                "/auth/register",
                json=build_register_payload(email="post-commit@example.com"),
                headers=self._origin_headers(),
            )

        self.assertEqual(response.status_code, 201)
        self._assert_sent_after_commit()

    def test_register_survives_a_dead_smtp(self) -> None:
        with self._smtp(fails=True):
            response = self.client.post(
                "/auth/register",
                json=build_register_payload(email="smtp-down@example.com"),
                headers=self._origin_headers(),
            )

        # El punto entero del refactor: la cuenta se crea igual.
        self.assertEqual(response.status_code, 201)
        self.assertIsNotNone(self._get_user("smtp-down@example.com"))

    # --- auth_r.py:251 · reenvio de verificacion ---------------------------

    def test_verify_request_sends_verification_only_after_commit(self) -> None:
        self._create_user(email="resend@example.com", verified=False)
        self.timeline.clear()

        with self._smtp():
            response = self.client.post(
                "/auth/email/verify/request",
                json={"email": "resend@example.com"},
                headers=self._origin_headers(),
            )

        self.assertEqual(response.status_code, 200)
        self._assert_sent_after_commit()

    def test_verify_request_survives_a_dead_smtp(self) -> None:
        self._create_user(email="resend-down@example.com", verified=False)

        with self._smtp(fails=True):
            response = self.client.post(
                "/auth/email/verify/request",
                json={"email": "resend-down@example.com"},
                headers=self._origin_headers(),
            )

        self.assertEqual(response.status_code, 200)

    # --- auth_r.py:300 · pedido de reset -----------------------------------

    def test_password_reset_request_sends_only_after_commit(self) -> None:
        self._create_user(email="reset-post@example.com", verified=True)
        self.timeline.clear()

        with self._smtp():
            response = self.client.post(
                "/auth/password/reset/request",
                json=build_password_reset_request_payload(email="reset-post@example.com"),
                headers=self._origin_headers(),
            )

        self.assertEqual(response.status_code, 200)
        self._assert_sent_after_commit()

    def test_password_reset_request_survives_a_dead_smtp(self) -> None:
        self._create_user(email="reset-down@example.com", verified=True)

        with self._smtp(fails=True):
            response = self.client.post(
                "/auth/password/reset/request",
                json=build_password_reset_request_payload(email="reset-down@example.com"),
                headers=self._origin_headers(),
            )

        self.assertEqual(response.status_code, 200)

    # --- auth_s.py:319 · cambio de email en el perfil ----------------------

    def _login_for_profile(self, email: str) -> None:
        self._create_user(email=email, verified=True)
        login_response = self._login(email=email)
        self.assertEqual(login_response.status_code, 200)
        self.timeline.clear()

    @staticmethod
    def _profile_payload(email: str) -> dict[str, str]:
        return {
            "first_name": "Ana",
            "last_name": "Lopez",
            "phone": "1122334455",
            "email": email,
        }

    def test_profile_email_change_sends_verification_only_after_commit(self) -> None:
        self._login_for_profile("old-address@example.com")

        with self._smtp():
            response = self.client.patch(
                "/auth/me",
                json=self._profile_payload("new-address@example.com"),
                headers=self._origin_headers(),
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["meta"]["verification_email_sent"])
        self._assert_sent_after_commit()

    def test_profile_email_change_survives_a_dead_smtp(self) -> None:
        self._login_for_profile("old-down@example.com")

        with self._smtp(fails=True):
            response = self.client.patch(
                "/auth/me",
                json=self._profile_payload("new-down@example.com"),
                headers=self._origin_headers(),
            )

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(self._get_user("new-down@example.com"))

    # --- la otra mitad de la regla: si no hay commit, no hay mail ----------

    def test_failed_transaction_sends_nothing(self) -> None:
        """La accion se encolo y despues la transaccion murio: nadie recibe nada.

        Se rompe `serialize_my_profile` porque corre *despues* del encolado, que
        es el unico orden en el que este test dice algo.
        """
        self._login_for_profile("kept@example.com")

        with self._smtp(), patch(
            "source.services.auth_s.serialize_my_profile",
            side_effect=RuntimeError("boom"),
        ):
            response = self.client.patch(
                "/auth/me",
                json=self._profile_payload("never-sent@example.com"),
                headers=self._origin_headers(),
            )

        self.assertEqual(response.status_code, 500)
        self.assertNotIn("send", self.timeline)
        self.assertIsNone(self._get_user("never-sent@example.com"))
        self.assertIsNotNone(self._get_user("kept@example.com"))
