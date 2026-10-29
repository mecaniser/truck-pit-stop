import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CustomerRepairContext from "./CustomerRepairContext";
import { customerContextApi as client, type CustomerContext } from "./customerContextApi";
import { createDemoConversations } from "./fixtures";
import { rememberConversation, restoredConversation } from "./inboxSelection";
vi.mock("./customerContextApi", () => ({customerContextApi: {context: vi.fn(), customers: vi.fn(), contacts: vi.fn(), repairs: vi.fn(), vehicles: vi.fn(), save: vi.fn(), linkRepair: vi.fn()}}));
const customer = {id: "customer-a", company_name: "Fleet A", display_name: "Owner A"};
const contact = {id: "driver-a", first_name: "Taylor", last_name: "Driver", role: "Driver", phone: "+15005550002", email: null};
const unlinked: CustomerContext = {version: 0, link_state: "unlinked", customer: null, contact: null, can_manage: true, default_scope: "contact", fleet_available: false};
const linked: CustomerContext = {...unlinked, version: 1, link_state: "linked", customer, contact, fleet_available: true};
const row = {...createDemoConversations()[0], id: "thread-a", customerId: null, conversationKind: "inquiry" as const};
const truck = {id: "truck-a", unit_number: "12", make: "Mack", model: "Anthem", year: 2020};
const repair = {id: "repair-a", order_number: "RO-100", status: "in_progress", created_at: "2026-10-28T12:00:00Z", description: "Brake inspection", vehicle: truck, linked_to_contact: true};
beforeEach(() => {
 vi.resetAllMocks(); sessionStorage.clear();
 vi.mocked(client.context).mockResolvedValue(linked);
 vi.mocked(client.repairs).mockResolvedValue({items: [repair], has_more: false, next_cursor: null});
 vi.mocked(client.vehicles).mockResolvedValue({items: [truck], has_more: false, next_cursor: null});
 vi.mocked(client.customers).mockResolvedValue({items: [customer]});
 vi.mocked(client.contacts).mockResolvedValue({items: [contact], has_more: false});
 vi.mocked(client.save).mockResolvedValue(linked);
 vi.mocked(client.linkRepair).mockResolvedValue({linked: true});
});
// jsdom has no layout observer; real layout/anchoring is covered in browser QA.
beforeEach(() => vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => vi.unstubAllGlobals());
afterEach(cleanup);
describe("customer repair context", () => {
 it("defaults to contact-linked repairs and requests fleet only explicitly", async () => {
  render(<CustomerRepairContext sessionKey="tenant-a:user-a" conversation={row} beforeNavigate={vi.fn()}/>);
  await screen.findByText("RO-100");
  expect(client.repairs).toHaveBeenCalledWith(row.id, "contact", "active", expect.any(AbortSignal));
  expect(client.repairs).not.toHaveBeenCalledWith(row.id, "fleet", expect.anything(), expect.anything());
  expect(screen.getByText("Taylor Driver")).toBeInTheDocument();
  expect(screen.getByText("Serviced trucks")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", {name: "Fleet history"}));
  await waitFor(() => expect(client.repairs).toHaveBeenLastCalledWith(row.id, "fleet", "all", expect.any(AbortSignal)));
  expect(screen.getByText("Fleet trucks")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", {name: "Repair status"}));
  fireEvent.click(screen.getByRole("option", {name: "History"}));
  await waitFor(() => expect(client.repairs).toHaveBeenLastCalledWith(row.id, "fleet", "history", expect.any(AbortSignal)));
 });
 it("shows one contact card and clears confirmation when changing the chosen person", async () => {
  render(<CustomerRepairContext sessionKey="tenant-a:user-a" conversation={row} beforeNavigate={vi.fn()}><p>Consent evidence</p></CustomerRepairContext>);
  await screen.findByText("Taylor Driver");
  expect(screen.getAllByText("Fleet A")).toHaveLength(1);
  expect(screen.getAllByText(row.identityLabel)).toHaveLength(1);
  expect(screen.getByText("Consent evidence")).toBeInTheDocument();
  expect(screen.queryByText("SMS contact")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", {name: "Change link"}));
  fireEvent.click(screen.getByRole("button", {name: "Person"}));
  fireEvent.click(await screen.findByRole("option", {name: "Taylor Driver · Driver"}));
  fireEvent.click(screen.getByRole("checkbox"));
  await waitFor(() => expect(screen.getByRole("button", {name: "Confirm link"})).toBeEnabled());
  fireEvent.click(screen.getByRole("button", {name: "Person"}));
  fireEvent.click(screen.getByRole("option", {name: "Add a person"}));
  expect(screen.getByRole("checkbox")).not.toBeChecked();
  expect(screen.getByRole("button", {name: "Confirm link"})).toBeDisabled();
  expect(client.save).not.toHaveBeenCalled();
 });
 it("links the chosen person only after confirmation and preserves transport identity", async () => {
  vi.mocked(client.context).mockResolvedValue(unlinked);
  const before = JSON.stringify(row);
  render(<CustomerRepairContext sessionKey="tenant-a:user-a" conversation={row} beforeNavigate={vi.fn()}/>);
  fireEvent.click(await screen.findByRole("button", {name: "Link customer"}));
  fireEvent.click(await screen.findByRole("button", {name: "Fleet A Owner A"}));
  fireEvent.click(await screen.findByRole("button", {name: "Person"}));
  fireEvent.click(await screen.findByRole("option", {name: "Taylor Driver · Driver"}));
  expect(screen.getByRole("button", {name: "Confirm link"})).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", {name: "Confirm link"}));
  await waitFor(() => expect(client.save).toHaveBeenCalledTimes(1));
  expect(client.save).toHaveBeenCalledWith(row.id, {action: "link", expected_version: 0, customer_id: customer.id, contact_id: contact.id}, expect.any(String));
  expect(JSON.stringify(row)).toBe(before);
 });
 it("creates atomically and retains the exact intent on uncertain retry", async () => {
  vi.mocked(client.context).mockResolvedValue(unlinked);
  vi.mocked(client.save).mockRejectedValueOnce(new Error("network unavailable"));
  render(<CustomerRepairContext sessionKey="tenant-a:user-a" conversation={row} beforeNavigate={vi.fn()}/>);
  fireEvent.click(await screen.findByRole("button", {name: "Add customer"}));
  for (const [name, value] of [["Company", "New Fleet"], ["First name", "Alex"], ["Last name", "Driver"], ["Email", "alex@example.test"]]) fireEvent.change(screen.getByRole("textbox", {name}), {target: {value}});
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", {name: "Create and link"}));
  await screen.findByRole("alert");
  expect(screen.getByRole("textbox", {name: "Company"})).toBeDisabled();
  fireEvent.click(screen.getByRole("button", {name: "Retry save"}));
  await waitFor(() => expect(client.save).toHaveBeenCalledTimes(2));
  expect(vi.mocked(client.save).mock.calls[0]).toEqual(vi.mocked(client.save).mock.calls[1]);
 });
 it("recovers an uncertain create after remount using its original version and key", async () => {
  const payload = {action: "create_contact" as const, expected_version: 0, customer_id: customer.id, contact: {first_name: "Taylor", last_name: "Driver", role: "Driver", email: null, phone: null}};
  sessionStorage.setItem(`inbox-customer-intent:tenant-a:user-a:${row.id}`, JSON.stringify({payload, key: "original-operation"}));
  // Context can already reflect the committed write while its response was lost.
  render(<CustomerRepairContext sessionKey="tenant-a:user-a" conversation={row} beforeNavigate={vi.fn()}/>);
  fireEvent.click(await screen.findByRole("button", {name: "Retry save"}));
  await waitFor(() => expect(client.save).toHaveBeenCalledWith(row.id, payload, "original-operation"));
  expect(sessionStorage.getItem(`inbox-customer-intent:tenant-a:user-a:${row.id}`)).toBeNull();
 });
 it("retries an unlinked saved contact intent without dereferencing a missing customer", async () => {
  vi.mocked(client.context).mockResolvedValue(unlinked);
  const payload = {action: "create_contact" as const, expected_version: 0, customer_id: customer.id, contact: {first_name: "Taylor", last_name: "Driver", role: "Driver", email: null, phone: null}};
  sessionStorage.setItem(`inbox-customer-intent:tenant-a:user-a:${row.id}`, JSON.stringify({payload, key: "unlinked-operation"}));
  render(<CustomerRepairContext sessionKey="tenant-a:user-a" conversation={row} beforeNavigate={vi.fn()}/>);
  fireEvent.click(await screen.findByRole("button", {name: "Retry save"}));
  await waitFor(() => expect(client.save).toHaveBeenCalledWith(row.id, payload, "unlinked-operation"));
 });
 it("confirms a fleet repair association explicitly", async () => {
  vi.mocked(client.repairs).mockResolvedValue({items: [{...repair, linked_to_contact: false}], has_more: false, next_cursor: null});
  render(<CustomerRepairContext sessionKey="tenant-a:user-a" conversation={row} beforeNavigate={vi.fn()}/>);
  fireEvent.click(await screen.findByRole("button", {name: "Fleet history"}));
  fireEvent.click(await screen.findByRole("button", {name: "Link to contact"}));
  expect(client.linkRepair).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", {name: "Confirm link"}));
  await waitFor(() => expect(client.linkRepair).toHaveBeenCalledWith(row.id, repair.id, 1, expect.any(String)));
 });
 it("paginates without changing scope and remembers selection only within tenant/user", async () => {
  vi.mocked(client.repairs).mockResolvedValueOnce({items: [repair], has_more: true, next_cursor: "cursor-a"}).mockResolvedValueOnce({items: [{...repair, id: "repair-b", order_number: "RO-101"}], has_more: false, next_cursor: null});
  render(<CustomerRepairContext sessionKey="tenant-a:user-a" conversation={row} beforeNavigate={vi.fn()}/>);
  fireEvent.click(await screen.findByRole("button", {name: "Load more repairs"}));
  await screen.findByText("RO-101");
  expect(screen.getByText("RO-100")).toBeInTheDocument();
  expect(client.repairs).toHaveBeenLastCalledWith(row.id, "contact", "active", expect.any(AbortSignal), "cursor-a");
  expect(screen.getByRole("link", {name: "RO-100 Open repair"})).toHaveAttribute("href", "/dashboard/repair-orders?selected=repair-a");
  const other = {...row, id: "other"}; rememberConversation(row.id, "tenant-a", "user-a");
  expect(restoredConversation([other, row], "tenant-a", "user-a")?.id).toBe(row.id);
  expect(restoredConversation([other, row], "tenant-b", "user-a")?.id).toBe(other.id);
 });
 it("discards aborted context responses when leaving", async () => {
  let resolve!: (value: CustomerContext) => void;
  vi.mocked(client.context).mockImplementationOnce(() => new Promise(r => {resolve = r;}));
  const view = render(<CustomerRepairContext sessionKey="tenant-a:user-a" conversation={row} beforeNavigate={vi.fn()}/>);
  view.unmount(); resolve(linked);
  await Promise.resolve(); expect(client.repairs).not.toHaveBeenCalled();
 });
});
