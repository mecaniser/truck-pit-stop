import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import MessageSettings from "./MessageSettings";
describe("Tenant Messages settings", () => {
  it("shows channel status only without registration controls", () => {
    const onClose = vi.fn();
    render(<MessageSettings deliveryMode="manual" channels={[{ channel: "sms", connected: true }]} onClose={onClose} />);
    expect(screen.getByText("Connected")).toBeVisible();
    expect(screen.getByText(/platform administrator manages/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Repair texting" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });
});
