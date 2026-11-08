import "@fontsource-variable/inter";
import "@fontsource-variable/space-grotesk";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "@mantine/spotlight/styles.css";
import "./styles/global.css";
import "./styles/effects.css";

import { ModalsProvider } from "@mantine/modals";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";

import { router } from "./app/router";
import { AppearanceProvider } from "./app/appearance";
import { isUnauthorized } from "./lib/api";
import { AuthProvider } from "./lib/auth";
import { LiveProvider } from "./lib/live";
import { installSpotlight } from "./lib/motion/spotlight";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (count, error) => !isUnauthorized(error) && count < 2,
    },
  },
});

installSpotlight();

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root element");

createRoot(root).render(
  <StrictMode>
    <AppearanceProvider>
      <Notifications position="bottom-right" limit={4} />
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <LiveProvider>
            <ModalsProvider>
              <RouterProvider router={router} />
            </ModalsProvider>
          </LiveProvider>
        </AuthProvider>
      </QueryClientProvider>
    </AppearanceProvider>
  </StrictMode>,
);
