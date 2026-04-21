import { useProfilePage } from "../features/profile";

export function ProfilePage() {
  const profilePage = useProfilePage();

  return (
    <section>
      <h1 className="page-title">Mi perfil</h1>
      <p className="page-subtitle">Administra tu cuenta desde el menu.</p>
      <div className="account-menu">
        <button
          className={`btn btn-small ${profilePage.section === "profile" ? "" : "btn-ghost"}`}
          type="button"
          onClick={() => profilePage.setSection("profile")}
        >
          Mi perfil
        </button>
        <button
          className={`btn btn-small ${profilePage.section === "history" ? "" : "btn-ghost"}`}
          type="button"
          onClick={() => profilePage.setSection("history")}
        >
          Historial de compras
        </button>
      </div>
      {profilePage.loading ? (
        <p>Cargando perfil...</p>
      ) : (
        <>
          {profilePage.section === "profile" && profilePage.profile && (
            <article className="card auth-wrap">
              <p><strong>Nombre:</strong> {profilePage.profile.first_name} {profilePage.profile.last_name}</p>
              <p className="muted">
                Estado email: {profilePage.profile.email_verified ? "Verificado" : "No verificado"}
              </p>
              {!profilePage.profile.email_verified && (
                <div className="checkout-actions">
                  <button
                    className="btn btn-small btn-ghost"
                    type="button"
                    onClick={() => void profilePage.onRequestEmailVerification()}
                    disabled={profilePage.verificationLoading}
                  >
                    {profilePage.verificationLoading ? "Enviando..." : "Verificar"}
                  </button>
                </div>
              )}
              <div className="checkout-row">
                <div>
                  <strong>Email:</strong>
                  {profilePage.editingField === "email" ? (
                    <input
                      className="input"
                      type="email"
                      value={profilePage.email}
                      onChange={(event) => profilePage.setEmail(event.target.value)}
                      required
                    />
                  ) : (
                    <p>{profilePage.profile.email}</p>
                  )}
                </div>
                <div className="admin-inline-actions">
                  {profilePage.editingField === "email" ? (
                    <>
                      <button className="btn btn-small" type="button" onClick={() => void profilePage.onSaveField("email")} disabled={profilePage.saving}>
                        {profilePage.saving ? "Guardando..." : "Guardar"}
                      </button>
                      <button className="btn btn-small btn-ghost" type="button" onClick={profilePage.onCancelEditing}>
                        Cancelar
                      </button>
                    </>
                  ) : (
                    <button className="btn btn-small btn-ghost" type="button" onClick={() => profilePage.onStartEditing("email")}>
                      Editar
                    </button>
                  )}
                </div>
              </div>
              <div className="checkout-row">
                <div>
                  <strong>Telefono:</strong>
                  {profilePage.editingField === "phone" ? (
                    <input
                      className="input"
                      value={profilePage.phone}
                      onChange={(event) => profilePage.setPhone(event.target.value)}
                      required
                    />
                  ) : (
                    <p>{profilePage.profile.phone || "-"}</p>
                  )}
                </div>
                <div className="admin-inline-actions">
                  {profilePage.editingField === "phone" ? (
                    <>
                      <button className="btn btn-small" type="button" onClick={() => void profilePage.onSaveField("phone")} disabled={profilePage.saving}>
                        {profilePage.saving ? "Guardando..." : "Guardar"}
                      </button>
                      <button className="btn btn-small btn-ghost" type="button" onClick={profilePage.onCancelEditing}>
                        Cancelar
                      </button>
                    </>
                  ) : (
                    <button className="btn btn-small btn-ghost" type="button" onClick={() => profilePage.onStartEditing("phone")}>
                      Editar
                    </button>
                  )}
                </div>
              </div>
            </article>
          )}

          {profilePage.section === "history" && (
            <div className="profile-orders">
              {profilePage.ordersLoading && <p>Cargando historial...</p>}
              {profilePage.ordersError && <p className="error">{profilePage.ordersError}</p>}
              {!profilePage.ordersLoading && !profilePage.ordersError && profilePage.orders.length === 0 && (
                <article className="card auth-wrap">
                  <p className="muted">Todavia no tenes compras registradas.</p>
                </article>
              )}
              {!profilePage.ordersLoading && !profilePage.ordersError && profilePage.orders.map((order) => (
                <article className="card" key={order.id}>
                  <p><strong>Orden #{order.id}</strong> - {order.status}</p>
                  <p className="muted">Total: ${(order.total_amount / 100).toLocaleString("es-AR")} {order.currency}</p>
                  <div className="profile-order-items">
                    {order.items.map((item) => (
                      <div className="checkout-row" key={item.id}>
                        <div>
                          <strong>{item.product_name || `Producto #${item.product_id}`}</strong>
                          <p className="muted">Variante: {item.variant_label}</p>
                        </div>
                        <div>
                          <p>Cant: {item.quantity}</p>
                          <p>Unit: ${(item.unit_price / 100).toLocaleString("es-AR")}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                  {(profilePage.paymentsByOrderId[order.id] ?? []).length > 0 && (
                    <div className="profile-order-items">
                      <h3 className="section-title">Pagos</h3>
                      {(profilePage.paymentsByOrderId[order.id] ?? []).map((payment) => (
                        <div className="checkout-row" key={payment.id}>
                          <div>
                            <strong>Pago #{payment.id}</strong>
                            <p className="muted">Metodo: {payment.method}</p>
                            <p className="muted">Estado: {payment.status}</p>
                            <p className="muted">Monto: ${(payment.amount / 100).toLocaleString("es-AR")} {payment.currency}</p>
                          </div>
                          {profilePage.isRetryableMercadoPagoPayment(payment) && order.status === "submitted" && (
                            <div className="auth-form" style={{ minWidth: 280 }}>
                              <p className="muted">Este pago no pudo completarse. Puedes generar un nuevo checkout.</p>
                              <button
                                className="btn btn-small"
                                type="button"
                                onClick={() => void profilePage.onRetryMercadoPago(order.id, payment.id)}
                                disabled={profilePage.retryingPaymentId !== null}
                              >
                                {profilePage.retryingPaymentId === payment.id ? "Redirigiendo..." : "Reintentar pago"}
                              </button>
                            </div>
                          )}
                          {payment.method === "mercadopago" && payment.status === "pending" && order.status === "submitted" && payment.provider_payload_data?.checkout?.checkout_url && (
                            <div className="auth-form" style={{ minWidth: 280 }}>
                              <p className="muted">Ya tienes un checkout activo para este intento.</p>
                              <button
                                className="btn btn-small btn-ghost"
                                type="button"
                                onClick={() => profilePage.onContinueMercadoPagoPayment(payment)}
                                disabled={profilePage.retryingPaymentId !== null}
                              >
                                Continuar pago
                              </button>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}
          {profilePage.error && <p className="error">{profilePage.error}</p>}
          {profilePage.success && <p className="success">{profilePage.success}</p>}
          {profilePage.retryError && <p className="error">{profilePage.retryError}</p>}
        </>
      )}
    </section>
  );
}
