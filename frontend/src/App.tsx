import { Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { Layout } from "./components/Layout";
import { AdminRoute } from "./guards/AdminRoute";
import { ProtectedRoute } from "./guards/ProtectedRoute";
import { AdminPage } from "./pages/AdminPage";
import { CategoriesPage } from "./pages/CategoriesPage";
import { CheckoutPage } from "./pages/CheckoutPage";
import { ContactPage } from "./pages/ContactPage";
import { ForgotPasswordPage } from "./pages/ForgotPasswordPage";
import { GroomingPage } from "./pages/GroomingPage";
import { LoginPage } from "./pages/LoginPage";
import { PaymentReturnPage } from "./pages/PaymentReturnPage";
import { ProductDetailPage } from "./pages/ProductDetailPage";
import { ProfilePage } from "./pages/ProfilePage";
import { RegisterPage } from "./pages/RegisterPage";
import { ResetPasswordPage } from "./pages/ResetPasswordPage";
import { StorefrontPage } from "./pages/StorefrontPage";
import { VerifyEmailPage } from "./pages/VerifyEmailPage";

export function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Navigate to="/home" replace />} />
          <Route path="/home" element={<StorefrontPage />} />
          <Route path="/categorias" element={<CategoriesPage />} />
          <Route path="/peluqueria" element={<GroomingPage />} />
          <Route path="/contacto" element={<ContactPage />} />
          <Route path="/checkout" element={<CheckoutPage />} />
          <Route path="/payments/success" element={<PaymentReturnPage variant="success" />} />
          <Route path="/payments/failure" element={<PaymentReturnPage variant="failure" />} />
          <Route path="/payments/pending" element={<PaymentReturnPage variant="pending" />} />
          <Route path="/products/:productId" element={<ProductDetailPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/verify-email" element={<VerifyEmailPage />} />

          <Route element={<ProtectedRoute />}>
            <Route path="/profile" element={<ProfilePage />} />
          </Route>

          <Route element={<AdminRoute />}>
            <Route path="/admin" element={<AdminPage />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </AuthProvider>
  );
}
