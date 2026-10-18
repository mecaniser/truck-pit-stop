import axios from "axios";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
const refresh = vi.hoisted(() => ({ legacy: vi.fn(), workos: vi.fn() }));
vi.mock("../../lib/authRefresh", () => ({
  requestTokenRefresh: refresh.legacy,
  requestWorkOSSessionRefresh: refresh.workos,
}));
vi.mock("../../lib/sessionKeepAlive", () => ({
  startSessionKeepAlive: vi.fn(),
  stopSessionKeepAlive: vi.fn(),
}));
import api from "../../lib/api";
import { useAuthStore } from "../../stores/authStore";
import ConnectedInbox from "./ConnectedInbox";
import { inboxApi } from "./api";
const originalAdapter = api.defaults.adapter;
beforeEach(() => {
  refresh.legacy.mockReset();
  refresh.workos.mockReset();
  useAuthStore.setState({
    isAuthenticated: false,
    token: null,
    refreshToken: null,
    authProvider: null,
    user: null,
    logoutInProgress: false,
  });
});
afterEach(() => {
  cleanup();
  api.defaults.adapter = originalAdapter;
});
describe("inbox bootstrap with real API interceptors", () => {
  it("shows login on signed-out401 without attempting missing-token renewal", async () => {
    api.defaults.adapter = async (config) => {
      const error = new axios.AxiosError(
        "Unauthorized",
        "ERR_BAD_REQUEST",
        config,
      );
      error.response = {
        status: 401,
        data: { detail: "Not authenticated" },
        statusText: "",
        headers: {},
        config,
      };
      throw error;
    };
    render(<ConnectedInbox />);
    expect(
      await screen.findByRole("heading", { name: "Sign in to Messages" }),
    ).toBeInTheDocument();
    expect(refresh.legacy).not.toHaveBeenCalled();
    expect(refresh.workos).not.toHaveBeenCalled();
  });
  it("still probes and accepts a cookie-only session", async () => {
    api.defaults.adapter = async (config) => ({
      status: 200,
      data: { tenant_id: "shop", user_id: "staff" },
      statusText: "OK",
      headers: {},
      config,
    });
    expect(await inboxApi.bootstrap()).toMatchObject({ tenant_id: "shop" });
  });
  it("retains WorkOS cookie renewal when the cookie expires", async () => {
    useAuthStore.setState({ authProvider: "workos", isAuthenticated: true });
    refresh.workos.mockResolvedValue({});
    let calls = 0;
    api.defaults.adapter = async (config) => {
      calls++;
      if (calls === 1) {
        const error = new axios.AxiosError(
          "Unauthorized",
          "ERR_BAD_REQUEST",
          config,
        );
        error.response = {
          status: 401,
          data: {},
          statusText: "",
          headers: {},
          config,
        };
        throw error;
      }
      return {
        status: 200,
        data: { tenant_id: "shop" },
        statusText: "OK",
        headers: {},
        config,
      };
    };
    expect(await inboxApi.bootstrap()).toMatchObject({ tenant_id: "shop" });
    expect(refresh.workos).toHaveBeenCalledTimes(1);
  });
});
