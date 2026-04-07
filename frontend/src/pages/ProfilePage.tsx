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
                            {payment.receipt_url ? <p className="success">Comprobante enviado.</p> : null}
                          </div>
                          {payment.method === "bank_transfer" && payment.status === "pending" && (
                            <div className="auth-form" style={{ minWidth: 280 }}>
                              <label>
                                Subir comprobante
                                <input
                                  className="input"
                                  type="file"
                                  accept=".jpg,.jpeg,.png,.pdf,image/jpeg,image/png,application/pdf"
                                  onChange={(event) =>
                                    profilePage.onSelectReceiptFile(payment.id, event.target.files?.[0] ?? null)
                                  }
                                />
                              </label>
                              <p className="muted">Formatos permitidos: JPG, PNG o PDF. Maximo 10 MB.</p>
                              <button
                                className="btn btn-small"
                                type="button"
                                onClick={() => void profilePage.onUploadReceipt(order.id, payment.id)}
                                disabled={
                                  profilePage.receiptUploadingPaymentId !== null ||
                                  !profilePage.receiptFiles[payment.id]
                                }
                              >
                                {profilePage.receiptUploadingPaymentId === payment.id ? "Subiendo..." : "Enviar comprobante"}
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
          {profilePage.receiptError && <p className="error">{profilePage.receiptError}</p>}
          {profilePage.receiptSuccess && <p className="success">{profilePage.receiptSuccess}</p>}
        </>
      )}
    </section>
  );
}
