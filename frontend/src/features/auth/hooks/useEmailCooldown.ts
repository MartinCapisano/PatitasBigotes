import { useCallback, useEffect, useState } from "react";
import {
  readEmailCooldownRemainingSeconds,
  startEmailCooldown,
  type EmailCooldownScope
} from "../verification-storage";

/**
 * Cuenta regresiva compartida por los dos envios de email de auth.
 *
 * El guard de `loading` cubre el doble click *durante* la request, pero apenas
 * termina el boton se puede apretar al instante: el backend responde 429 y el
 * usuario ve el texto crudo en ingles. Esto hace que ese 429 deje de ser
 * alcanzable con un click normal.
 *
 * El valor se recalcula desde el storage en cada tick en vez de decrementar un
 * contador, asi una pestana dormida no se despierta con la cuenta atrasada.
 */
export function useEmailCooldown(scope: EmailCooldownScope) {
  const [remainingSeconds, setRemainingSeconds] = useState(() =>
    readEmailCooldownRemainingSeconds(scope)
  );
  const active = remainingSeconds > 0;

  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => {
      setRemainingSeconds(readEmailCooldownRemainingSeconds(scope));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [active, scope]);

  const start = useCallback(() => {
    startEmailCooldown(scope);
    setRemainingSeconds(readEmailCooldownRemainingSeconds(scope));
  }, [scope]);

  return { remainingSeconds, active, start };
}
