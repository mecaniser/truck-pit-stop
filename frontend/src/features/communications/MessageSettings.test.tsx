import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import MessageSettings from "./MessageSettings";
vi.mock("./SMSSetup", () => ({ default: () => <input aria-label="Registration draft" /> }));
describe("Messages settings", () => {
  it("combines channels and registration while retaining registration edits between sections", () => {
    render(<MessageSettings canSetupSMS deliveryMode="manual" channels={[{ channel: "sms", connected: true }]} onClose={vi.fn()} />);
    expect(screen.getByText("Connected")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "SMS setup" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Registration draft" }), { target: { value: "Fleet" } });
    fireEvent.click(screen.getByRole("button", { name: "Channels" }));
    fireEvent.click(screen.getByRole("button", { name: "SMS setup" }));
    expect(screen.getByRole("textbox", { name: "Registration draft" })).toHaveValue("Fleet");
  });
  it("keeps registration unavailable to roles without setup permission and closes on Escape", () => {
    const onClose = vi.fn();
    render(<MessageSettings canSetupSMS={false} onClose={onClose} />);
    expect(screen.queryByRole("button", { name: "SMS setup" })).not.toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });
});
