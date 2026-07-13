import { useState } from "react";
import {
  ADMIN_SALES_SECTIONS,
  ADMIN_VIEW_SECTIONS,
  type AdminMode,
  type AdminSection,
  formatArs,
  useAdminCatalog,
  useAdminDiscounts,
  useAdminPaymentIncidents,
  useAdminOrdersPayments,
  useAdminRegisterPayment,
  useAdminSales,
  useAdminTurns
} from "../features/admin";
import {
  AdminSectionTabs,
  CategoriesSection,
  CatalogSection,
  DiscountsSection,
  OrdersPaymentsSection,
  PaymentIncidentsSection,
  RegisterPaymentSection,
  SalesSection,
  TurnsSection
} from "../features/admin/components";

export function AdminPage() {
  const [adminMode, setAdminMode] = useState<AdminMode>("ver");
  const [viewSection, setViewSection] = useState<AdminSection>("catalogo");
  const [salesSection, setSalesSection] = useState<AdminSection>("registrar_venta");

  const adminSection = adminMode === "ver" ? viewSection : salesSection;

  const catalog = useAdminCatalog();
  const turns = useAdminTurns(adminSection);
  const discounts = useAdminDiscounts({
    adminSection,
    categories: catalog.categories,
    productsSorted: catalog.productsSorted,
    variantsByProduct: catalog.variantsByProduct
  });
  const ordersPayments = useAdminOrdersPayments({ adminSection });
  const paymentIncidents = useAdminPaymentIncidents({ adminSection });
  const sales = useAdminSales({
    adminSection,
    productsSorted: catalog.productsSorted,
    variantsByProduct: catalog.variantsByProduct
  });
  const registerPayment = useAdminRegisterPayment({ adminSection });
  const productsCountByCategory = Object.fromEntries(
    catalog.productsSorted.reduce<Array<[string, number]>>((acc, product) => {
      const categoryName = String(product.category || "Sin categoria");
      const current = acc.find(([name]) => name === categoryName);
      if (current) {
        current[1] += 1;
      } else {
        acc.push([categoryName, 1]);
      }
      return acc;
    }, [])
  );

  return (
    <section>
      <h1 className="page-title">Panel Admin</h1>
      <p className="page-subtitle">Trabaja el panel por bloques: ver para gestionar y revisar, venta para operar cobros, ventas e incidencias.</p>
      <div className="account-menu">
        <button
          className={`btn btn-small ${adminMode === "ver" ? "" : "btn-ghost"}`}
          type="button"
          onClick={() => setAdminMode("ver")}
        >
          Ver
        </button>
        <button
          className={`btn btn-small ${adminMode === "venta" ? "" : "btn-ghost"}`}
          type="button"
          onClick={() => setAdminMode("venta")}
        >
          Venta
        </button>
      </div>
      <AdminSectionTabs
        adminSection={adminSection}
        sections={adminMode === "ver" ? ADMIN_VIEW_SECTIONS : ADMIN_SALES_SECTIONS}
        onSelect={(section) => {
          if (ADMIN_VIEW_SECTIONS.includes(section)) {
            setViewSection(section);
            setAdminMode("ver");
            return;
          }
          setSalesSection(section);
          setAdminMode("venta");
        }}
      />

      {adminSection === "categorias" && (
        <CategoriesSection
          categories={catalog.categories}
          productsCountByCategory={productsCountByCategory}
          error={catalog.error}
          editingCategoryId={catalog.editingCategoryId}
          setEditingCategoryId={catalog.setEditingCategoryId}
          editCategoryName={catalog.editCategoryName}
          setEditCategoryName={catalog.setEditCategoryName}
          openCategoryMenuId={catalog.openCategoryMenuId}
          setOpenCategoryMenuId={catalog.setOpenCategoryMenuId}
          onStartCategoryEdit={catalog.onStartCategoryEdit}
          onSaveCategoryEdit={catalog.onSaveCategoryEdit}
        />
      )}

      {adminSection === "descuentos" && (
        <DiscountsSection
          discountsError={discounts.discountsError}
          discountsLoading={discounts.discountsLoading}
          discounts={discounts.discounts}
          showCreateDiscountForm={discounts.showCreateDiscountForm}
          setShowCreateDiscountForm={discounts.setShowCreateDiscountForm}
          loadDiscounts={discounts.loadDiscounts}
          newDiscountName={discounts.newDiscountName}
          setNewDiscountName={discounts.setNewDiscountName}
          newDiscountType={discounts.newDiscountType}
          setNewDiscountType={discounts.setNewDiscountType}
          newDiscountValue={discounts.newDiscountValue}
          setNewDiscountValue={discounts.setNewDiscountValue}
          newDiscountTarget={discounts.newDiscountTarget}
          setNewDiscountTarget={discounts.setNewDiscountTarget}
          newDiscountCategoryId={discounts.newDiscountCategoryId}
          setNewDiscountCategoryId={discounts.setNewDiscountCategoryId}
          categories={discounts.categories}
          newDiscountActive={discounts.newDiscountActive}
          setNewDiscountActive={discounts.setNewDiscountActive}
          showDiscountProductPicker={discounts.showDiscountProductPicker}
          setShowDiscountProductPicker={discounts.setShowDiscountProductPicker}
          selectedDiscountProductCount={discounts.selectedDiscountProductCount}
          selectedDiscountVariantCount={discounts.selectedDiscountVariantCount}
          productsSorted={discounts.productsSorted}
          variantsByProduct={discounts.variantsByProduct}
          discountPickerExpandedProducts={discounts.discountPickerExpandedProducts}
          toggleDiscountPickerProductExpanded={discounts.toggleDiscountPickerProductExpanded}
          selectedDiscountProductIds={discounts.selectedDiscountProductIds}
          selectedDiscountVariantIds={discounts.selectedDiscountVariantIds}
          toggleDiscountProductSelection={discounts.toggleDiscountProductSelection}
          toggleDiscountVariantSelection={discounts.toggleDiscountVariantSelection}
          onCreateDiscount={discounts.onCreateDiscount}
          onToggleDiscountActive={discounts.onToggleDiscountActive}
          togglingDiscountId={discounts.togglingDiscountId}
          discountPendingDeleteId={discounts.discountPendingDeleteId}
          deletingDiscount={discounts.deletingDiscount}
          onRequestDeleteDiscount={discounts.onRequestDeleteDiscount}
          onCancelDeleteDiscount={discounts.onCancelDeleteDiscount}
          onConfirmDeleteDiscount={discounts.onConfirmDeleteDiscount}
          formatArs={formatArs}
        />
      )}

      {adminSection === "catalogo" && (
        <CatalogSection
          error={catalog.error}
          showCreateProductForm={catalog.showCreateProductForm}
          setShowCreateProductForm={catalog.setShowCreateProductForm}
          onCreateProduct={catalog.onCreateProduct}
          savingNew={catalog.savingNew}
          newName={catalog.newName}
          setNewName={catalog.setNewName}
          newCategory={catalog.newCategory}
          setNewCategory={catalog.setNewCategory}
          categories={catalog.categories}
          productsSorted={catalog.productsSorted}
          categoryNames={catalog.categoryNames}
          catalogCategoryFilter={catalog.catalogCategoryFilter}
          setCatalogCategoryFilter={catalog.setCatalogCategoryFilter}
          showAddStockModal={catalog.showAddStockModal}
          setShowAddStockModal={catalog.setShowAddStockModal}
          stockProductId={catalog.stockProductId}
          setStockProductId={catalog.setStockProductId}
          stockQuantity={catalog.stockQuantity}
          setStockQuantity={catalog.setStockQuantity}
          addingStock={catalog.addingStock}
          stockSuccessMessage={catalog.stockSuccessMessage}
          onOpenAddStockModal={catalog.onOpenAddStockModal}
          onConfirmAddStock={catalog.onConfirmAddStock}
          showCreateCategoryForm={catalog.showCreateCategoryForm}
          setShowCreateCategoryForm={catalog.setShowCreateCategoryForm}
          onCreateCategory={catalog.onCreateCategory}
          showDeleteCategoryModal={catalog.showDeleteCategoryModal}
          setShowDeleteCategoryModal={catalog.setShowDeleteCategoryModal}
          deleteCategoryId={catalog.deleteCategoryId}
          setDeleteCategoryId={catalog.setDeleteCategoryId}
          deletingCategory={catalog.deletingCategory}
          deletableCategories={catalog.deletableCategories}
          onOpenDeleteCategoryModal={catalog.onOpenDeleteCategoryModal}
          onConfirmDeleteCategory={catalog.onConfirmDeleteCategory}
          newCategoryName={catalog.newCategoryName}
          setNewCategoryName={catalog.setNewCategoryName}
          creatingCategory={catalog.creatingCategory}
          newDescription={catalog.newDescription}
          setNewDescription={catalog.setNewDescription}
          newImgUrl={catalog.newImgUrl}
          setNewImgUrl={catalog.setNewImgUrl}
          loading={catalog.loading}
          visibleProducts={catalog.visibleProducts}
          productsByCategory={catalog.productsByCategory}
          variantsByProduct={catalog.variantsByProduct}
          expandedProducts={catalog.expandedProducts}
          toggleProductExpanded={catalog.toggleProductExpanded}
          openProductMenuId={catalog.openProductMenuId}
          setOpenProductMenuId={catalog.setOpenProductMenuId}
          onStartEdit={catalog.onStartEdit}
          productPendingDeleteId={catalog.productPendingDeleteId}
          deletingProduct={catalog.deletingProduct}
          onRequestDeleteProduct={catalog.onRequestDeleteProduct}
          onCancelDeleteProduct={catalog.onCancelDeleteProduct}
          onConfirmDeleteProduct={catalog.onConfirmDeleteProduct}
          editingProductId={catalog.editingProductId}
          editName={catalog.editName}
          setEditName={catalog.setEditName}
          editCategory={catalog.editCategory}
          setEditCategory={catalog.setEditCategory}
          editDescription={catalog.editDescription}
          setEditDescription={catalog.setEditDescription}
          editImgUrl={catalog.editImgUrl}
          setEditImgUrl={catalog.setEditImgUrl}
          editActive={catalog.editActive}
          setEditActive={catalog.setEditActive}
          onSaveProductEdit={catalog.onSaveProductEdit}
          setEditingProductId={catalog.setEditingProductId}
          editingVariantId={catalog.editingVariantId}
          onStartVariantEdit={catalog.onStartVariantEdit}
          editVariantSku={catalog.editVariantSku}
          setEditVariantSku={catalog.setEditVariantSku}
          editVariantSize={catalog.editVariantSize}
          setEditVariantSize={catalog.setEditVariantSize}
          editVariantColor={catalog.editVariantColor}
          setEditVariantColor={catalog.setEditVariantColor}
          editVariantImgUrl={catalog.editVariantImgUrl}
          setEditVariantImgUrl={catalog.setEditVariantImgUrl}
          editVariantStock={catalog.editVariantStock}
          setEditVariantStock={catalog.setEditVariantStock}
          editVariantActive={catalog.editVariantActive}
          setEditVariantActive={catalog.setEditVariantActive}
          enableVariantPriceEdit={catalog.enableVariantPriceEdit}
          setEnableVariantPriceEdit={catalog.setEnableVariantPriceEdit}
          editVariantPrice={catalog.editVariantPrice}
          setEditVariantPrice={catalog.setEditVariantPrice}
          onSaveVariantEdit={catalog.onSaveVariantEdit}
          setEditingVariantId={catalog.setEditingVariantId}
          variantPriceConfirmation={catalog.variantPriceConfirmation}
          savingVariant={catalog.savingVariant}
          onCancelVariantPriceChange={catalog.onCancelVariantPriceChange}
          onConfirmVariantPriceChange={catalog.onConfirmVariantPriceChange}
          formatArs={formatArs}
        />
      )}

      {adminSection === "turnos" && (
        <TurnsSection
          turns={turns.turns}
          turnsError={turns.turnsError}
          turnsFilter={turns.turnsFilter}
          setTurnsFilter={turns.setTurnsFilter}
          loadTurns={turns.loadTurns}
          onUpdateTurnStatus={turns.onUpdateTurnStatus}
        />
      )}

      {(adminSection === "ordenes" || adminSection === "pagos") && (
        <OrdersPaymentsSection
          adminSection={adminSection}
          orderError={ordersPayments.orderError}
          ordersFilter={ordersPayments.ordersFilter}
          setOrdersFilter={ordersPayments.setOrdersFilter}
          ordersSortBy={ordersPayments.ordersSortBy}
          setOrdersSortBy={ordersPayments.setOrdersSortBy}
          ordersSortDir={ordersPayments.ordersSortDir}
          setOrdersSortDir={ordersPayments.setOrdersSortDir}
          ordersShowAll={ordersPayments.ordersShowAll}
          setOrdersShowAll={ordersPayments.setOrdersShowAll}
          ordersListLoading={ordersPayments.ordersListLoading}
          ordersList={ordersPayments.ordersList}
          loadAdminOrder={ordersPayments.loadAdminOrder}
          loadingOrderDetail={ordersPayments.loadingOrderDetail}
          closeSelectedOrder={ordersPayments.closeSelectedOrder}
          paymentsFilter={ordersPayments.paymentsFilter}
          setPaymentsFilter={ordersPayments.setPaymentsFilter}
          paymentsSortBy={ordersPayments.paymentsSortBy}
          setPaymentsSortBy={ordersPayments.setPaymentsSortBy}
          paymentsSortDir={ordersPayments.paymentsSortDir}
          setPaymentsSortDir={ordersPayments.setPaymentsSortDir}
          paymentsShowAll={ordersPayments.paymentsShowAll}
          setPaymentsShowAll={ordersPayments.setPaymentsShowAll}
          paymentsListLoading={ordersPayments.paymentsListLoading}
          paymentsList={ordersPayments.paymentsList}
          selectedOrder={ordersPayments.selectedOrder}
          orderPayments={ordersPayments.orderPayments}
          formatArs={formatArs}
        />
      )}

      {adminSection === "incidencias_pago" && (
        <PaymentIncidentsSection
          error={paymentIncidents.error}
          success={paymentIncidents.success}
          loading={paymentIncidents.loading}
          incidents={paymentIncidents.incidents}
          resolveWithRefund={paymentIncidents.resolveWithRefund}
          resolveWithoutRefund={paymentIncidents.resolveWithoutRefund}
          processingIncidentId={paymentIncidents.processingIncidentId}
          formatArs={formatArs}
        />
      )}

      {adminSection === "registrar_venta" && (
        <SalesSection
          firstName={sales.firstName}
          setFirstName={sales.setFirstName}
          lastName={sales.lastName}
          setLastName={sales.setLastName}
          email={sales.email}
          setEmail={sales.setEmail}
          phone={sales.phone}
          setPhone={sales.setPhone}
          dni={sales.dni}
          setDni={sales.setDni}
          selectedUser={sales.selectedUser}
          onClearSelectedUser={sales.onClearSelectedUser}
          showUserSearch={sales.showUserSearch}
          openUserSearchModal={sales.openUserSearchModal}
          closeUserSearchModal={sales.closeUserSearchModal}
          searchFirstName={sales.searchFirstName}
          setSearchFirstName={sales.setSearchFirstName}
          searchLastName={sales.searchLastName}
          setSearchLastName={sales.setSearchLastName}
          searchEmail={sales.searchEmail}
          setSearchEmail={sales.setSearchEmail}
          searchDni={sales.searchDni}
          setSearchDni={sales.setSearchDni}
          searchPhone={sales.searchPhone}
          setSearchPhone={sales.setSearchPhone}
          searchLoading={sales.searchLoading}
          searchError={sales.searchError}
          searchResults={sales.searchResults}
          pendingSelectedUser={sales.pendingSelectedUser}
          onTogglePendingUser={sales.onTogglePendingUser}
          onConfirmPendingUser={sales.onConfirmPendingUser}
          showProductSearch={sales.showProductSearch}
          openProductSearchModal={sales.openProductSearchModal}
          closeProductSearchModal={sales.closeProductSearchModal}
          productSearchQuery={sales.productSearchQuery}
          setProductSearchQuery={sales.setProductSearchQuery}
          productSearchResults={sales.productSearchResults}
          pendingSelectedProductId={sales.pendingSelectedProductId}
          onTogglePendingProduct={sales.onTogglePendingProduct}
          onConfirmPendingProduct={sales.onConfirmPendingProduct}
          selectedProduct={sales.selectedProduct}
          onClearSelectedProduct={sales.onClearSelectedProduct}
          selectedProductVariants={sales.selectedProductVariants}
          newVariantId={sales.newVariantId}
          setNewVariantId={sales.setNewVariantId}
          newQuantity={sales.newQuantity}
          setNewQuantity={sales.setNewQuantity}
          items={sales.items}
          total={sales.total}
          onAddItem={sales.onAddItem}
          removeItem={sales.removeItem}
          registerPayment={sales.registerPayment}
          setRegisterPayment={sales.setRegisterPayment}
          paymentMethod={sales.paymentMethod}
          setPaymentMethod={sales.setPaymentMethod}
          amountPaid={sales.amountPaid}
          setAmountPaid={sales.setAmountPaid}
          changeAmount={sales.changeAmount}
          setChangeAmount={sales.setChangeAmount}
          paymentRef={sales.paymentRef}
          setPaymentRef={sales.setPaymentRef}
          saving={sales.saving}
          error={sales.error}
          success={sales.success}
          onSubmit={sales.onSubmit}
          formatArs={formatArs}
        />
      )}

      {adminSection === "registrar_pago" && (
        <RegisterPaymentSection
          selectedUser={registerPayment.selectedUser}
          onClearSelectedUser={registerPayment.onClearSelectedUser}
          showUserSearch={registerPayment.showUserSearch}
          openUserSearchModal={registerPayment.openUserSearchModal}
          closeUserSearchModal={registerPayment.closeUserSearchModal}
          searchFirstName={registerPayment.searchFirstName}
          setSearchFirstName={registerPayment.setSearchFirstName}
          searchLastName={registerPayment.searchLastName}
          setSearchLastName={registerPayment.setSearchLastName}
          searchEmail={registerPayment.searchEmail}
          setSearchEmail={registerPayment.setSearchEmail}
          searchDni={registerPayment.searchDni}
          setSearchDni={registerPayment.setSearchDni}
          searchPhone={registerPayment.searchPhone}
          setSearchPhone={registerPayment.setSearchPhone}
          searchLoading={registerPayment.searchLoading}
          searchError={registerPayment.searchError}
          searchResults={registerPayment.searchResults}
          pendingSelectedUser={registerPayment.pendingSelectedUser}
          onTogglePendingUser={registerPayment.onTogglePendingUser}
          onConfirmPendingUser={registerPayment.onConfirmPendingUser}
          pendingPayments={registerPayment.pendingPayments}
          pendingPaymentsLoading={registerPayment.pendingPaymentsLoading}
          pendingPaymentsError={registerPayment.pendingPaymentsError}
          selectedPaymentId={registerPayment.selectedPaymentId}
          setSelectedPaymentId={registerPayment.setSelectedPaymentId}
          selectedPayment={registerPayment.selectedPayment}
          selectedMethod={registerPayment.selectedMethod}
          paidAmount={registerPayment.paidAmount}
          setPaidAmount={registerPayment.setPaidAmount}
          changeAmount={registerPayment.changeAmount}
          setChangeAmount={registerPayment.setChangeAmount}
          paymentRef={registerPayment.paymentRef}
          setPaymentRef={registerPayment.setPaymentRef}
          saving={registerPayment.saving}
          error={registerPayment.error}
          success={registerPayment.success}
          showConfirmModal={registerPayment.showConfirmModal}
          setShowConfirmModal={registerPayment.setShowConfirmModal}
          onOpenConfirm={registerPayment.onOpenConfirm}
          onConfirmPayment={registerPayment.onConfirmPayment}
          formatArs={formatArs}
        />
      )}
    </section>
  );
}
