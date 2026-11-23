import { BrowserRouter, Route, Routes } from "react-router-dom";
import { CountryProvider, CountryUrlSync } from "./country-context";
import { AppLayout } from "./app-layout";
import { RequireSession } from "./require-session";
import BindingEditPage from "../pages/BindingEditPage";
import BindingWizardPage from "../pages/BindingWizardPage";
import BindingsPage from "../pages/BindingsPage";
import BootstrapPage from "../pages/BootstrapPage";
import CatalogChangesPage from "../pages/CatalogChangesPage";
import CollectionDetailPage from "../pages/CollectionDetailPage";
import CollectionEditPage from "../pages/CollectionEditPage";
import CollectionsPage from "../pages/CollectionsPage";
import DashboardPage from "../pages/DashboardPage";
import HelpPage from "../pages/HelpPage";
import LoginPage from "../pages/LoginPage";
import NotFoundPage from "../pages/NotFoundPage";
import ProvidersPage from "../pages/ProvidersPage";
import RunDetailPage from "../pages/RunDetailPage";
import RunsPage from "../pages/RunsPage";
import SettingsPage from "../pages/SettingsPage";

export default function App() {
  return (
    <BrowserRouter>
      <CountryProvider>
        <CountryUrlSync />
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/bootstrap" element={<BootstrapPage />} />
          <Route
            path="/app"
            element={
              <RequireSession>
                <AppLayout />
              </RequireSession>
            }
          >
            <Route index element={<DashboardPage />} />
            <Route path="catalog-changes" element={<CatalogChangesPage />} />
            <Route path="providers" element={<ProvidersPage />} />
            <Route path="collections" element={<CollectionsPage />} />
            <Route path="collections/:collectionId" element={<CollectionDetailPage />} />
            <Route path="collections/new" element={<CollectionEditPage />} />
            <Route path="collections/:collectionId/edit" element={<CollectionEditPage />} />
            <Route path="bindings" element={<BindingsPage />} />
            <Route path="bindings/new" element={<BindingWizardPage />} />
            <Route path="bindings/:bindingId/edit" element={<BindingEditPage />} />
            <Route path="runs" element={<RunsPage />} />
            <Route path="runs/:runId" element={<RunDetailPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="help" element={<HelpPage />} />
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </CountryProvider>
    </BrowserRouter>
  );
}
