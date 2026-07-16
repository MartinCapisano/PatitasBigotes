from backend.tests.http._base import HttpFundamentalsBase


class HttpUsersSearchResolveFundamentalsTests(HttpFundamentalsBase):
    def _login_as_admin(self, *, email: str = "users-search-admin@example.com") -> None:
        self._create_user(email=email, is_admin=True, verified=True)
        login_response = self._login(email=email)
        self.assertEqual(login_response.status_code, 200)

    # -- GET /users/search --

    def test_search_users_requires_admin_over_http(self) -> None:
        response = self.client.get("/users/search", params={"email": "someone@example.com"})
        self.assertEqual(response.status_code, 401)

        self._create_user(email="users-search-regular@example.com", verified=True)
        login_response = self._login(email="users-search-regular@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.get("/users/search", params={"email": "someone@example.com"})
        self.assertEqual(response.status_code, 403)

    def test_search_users_requires_at_least_one_filter_over_http(self) -> None:
        self._login_as_admin()

        response = self.client.get("/users/search")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "at least one search filter is required")

    def test_search_users_by_email_over_http(self) -> None:
        self._create_user(email="findme@example.com", verified=True)
        self._login_as_admin()

        response = self.client.get("/users/search", params={"email": "findme@example.com"})

        self.assertEqual(response.status_code, 200)
        rows = response.json()["data"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["email"], "findme@example.com")

    def test_search_users_by_name_is_case_insensitive_partial_match_over_http(self) -> None:
        self._create_user(email="jane-search@example.com", verified=True)
        self._login_as_admin()

        response = self.client.get("/users/search", params={"first_name": "tes"})

        self.assertEqual(response.status_code, 200)
        rows = response.json()["data"]
        self.assertTrue(any(row["email"] == "jane-search@example.com" for row in rows))

    def test_search_users_no_match_returns_empty_list_over_http(self) -> None:
        self._login_as_admin()

        response = self.client.get("/users/search", params={"email": "nobody@example.com"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], [])

    # -- POST /users/resolve --

    def _resolve_payload(self, **overrides) -> dict:
        payload = {
            "first_name": "Guest",
            "last_name": "Buyer",
            "email": "guest-resolve@example.com",
            "phone": "1122334455",
        }
        payload.update(overrides)
        return payload

    def test_resolve_user_requires_admin_over_http(self) -> None:
        response = self.client.post(
            "/users/resolve",
            json=self._resolve_payload(),
            headers=self._origin_headers(),
        )
        self.assertEqual(response.status_code, 401)

    def test_resolve_user_creates_new_guest_over_http(self) -> None:
        self._login_as_admin()

        response = self.client.post(
            "/users/resolve",
            json=self._resolve_payload(),
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertTrue(payload["created"])
        self.assertEqual(payload["user"]["email"], "guest-resolve@example.com")
        self.assertFalse(payload["user"]["has_account"])

    def test_resolve_user_returns_existing_user_without_creating_duplicate_over_http(self) -> None:
        self._login_as_admin()
        first_response = self.client.post(
            "/users/resolve",
            json=self._resolve_payload(),
            headers=self._origin_headers(),
        )
        self.assertTrue(first_response.json()["data"]["created"])
        first_user_id = first_response.json()["data"]["user"]["id"]

        second_response = self.client.post(
            "/users/resolve",
            json=self._resolve_payload(),
            headers=self._origin_headers(),
        )

        self.assertEqual(second_response.status_code, 200)
        payload = second_response.json()["data"]
        self.assertFalse(payload["created"])
        self.assertEqual(payload["user"]["id"], first_user_id)

    def test_resolve_user_rejects_mismatched_contact_for_existing_email_over_http(self) -> None:
        self._login_as_admin()
        self.client.post(
            "/users/resolve",
            json=self._resolve_payload(),
            headers=self._origin_headers(),
        )

        response = self.client.post(
            "/users/resolve",
            json=self._resolve_payload(first_name="Different Name"),
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"],
            "contact data does not match existing user for this email",
        )

    def test_resolve_user_rejects_missing_required_field_over_http(self) -> None:
        self._login_as_admin()

        response = self.client.post(
            "/users/resolve",
            json={"first_name": "Guest", "last_name": "Buyer", "email": "no-phone@example.com"},
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 422)
