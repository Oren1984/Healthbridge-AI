import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import App from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ApiError } from "./lib/api";
import { AuthProvider } from "./lib/auth";
import { I18nProvider } from "./lib/i18n";
import { applyTheme, getThemePref } from "./lib/theme";
import "./styles.css";

applyTheme(getThemePref());

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 2,
      refetchOnWindowFocus: false,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <BrowserRouter>
          <AuthProvider>
            <ErrorBoundary><App /></ErrorBoundary>
          </AuthProvider>
        </BrowserRouter>
      </I18nProvider>
    </QueryClientProvider>
  </StrictMode>,
);
