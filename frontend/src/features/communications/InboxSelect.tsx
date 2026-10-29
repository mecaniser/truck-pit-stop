import { Listbox, ListboxButton, ListboxOption, ListboxOptions } from "@headlessui/react";
import { Check, ChevronDown } from "lucide-react";
import "./inboxSelect.css";

/** Compact, keyboard-accessible menu shared by the inbox and its dialogs. */
export default function InboxSelect({label, value, options, onChange, disabled = false}: {
  label: string; value: string; options: {value: string; label: string}[];
  onChange: (value: string) => void; disabled?: boolean;
}) {
  return <Listbox value={value} onChange={onChange} disabled={disabled}>
    <ListboxButton aria-label={label} className="inbox-select-button">
      <span>{options.find(option => option.value === value)?.label ?? "Choose…"}</span>
      <ChevronDown size={14} aria-hidden="true" />
    </ListboxButton>
    <ListboxOptions anchor="bottom start" className="inbox-select-options">
      {options.map(option => <ListboxOption key={option.value} value={option.value} className="inbox-select-option">
        {({selected}) => <><span>{option.label}</span>{selected && <Check size={14} aria-hidden="true" />}</>}
      </ListboxOption>)}
    </ListboxOptions>
  </Listbox>;
}
