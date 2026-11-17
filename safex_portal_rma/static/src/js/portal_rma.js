import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Dialog } from "@web/core/dialog/dialog";
import { Component, onMounted, useRef, useState } from "@odoo/owl";

async function verifyDevice(serialNo, imei) {
    return rpc("/my/rma/verify_device", { serial_no: serialNo, imei: imei });
}

const ACCESSORY_TEXTS = {
    acc_battery: {
        kind: "battery",
        title: _t("Battery Serial Number"),
        label: _t("Enter the serial number printed on the battery you send."),
        placeholder: _t("Battery serial number"),
    },
    acc_dock: {
        kind: "dock",
        title: _t("Docking Station Serial Number"),
        label: _t("Enter the serial number printed on the docking station you send."),
        placeholder: _t("Docking station serial number"),
    },
};

/** Pop-up asking the battery / docking station serial number, verified before it is accepted. */
class AccessorySerialDialog extends Component {
    static template = "safex_portal_rma.AccessorySerialDialog";
    static components = { Dialog };
    static props = {
        kind: String,
        title: String,
        label: String,
        placeholder: String,
        serial: { type: String, optional: true },
        onVerified: Function,
        close: Function,
    };

    setup() {
        this.state = useState({ serial: this.props.serial || "", message: "", busy: false });
        this.serialInput = useRef("serialInput");
        onMounted(() => this.serialInput.el?.focus());
    }

    async onVerify() {
        const serial = this.state.serial.trim();
        if (!serial) {
            this.state.message = _t("Enter the serial number.");
            return;
        }
        this.state.busy = true;
        try {
            const result = await rpc("/my/rma/verify_accessory", { kind: this.props.kind, serial_no: serial });
            if (result.verified) {
                this.props.onVerified(result.serial_no);
                this.props.close();
            } else {
                this.state.message = result.message || _t("Serial number not found.");
            }
        } finally {
            this.state.busy = false;
        }
    }
}

function renderResult(container, result) {
    container.replaceChildren();
    const alert = document.createElement("div");
    alert.setAttribute("role", "alert");
    if (result.verified && result.status === "other_dealer") {
        // CR-04: sold through another dealer: only the product and that dealer are shown.
        alert.className = "alert alert-warning mb-0";
        alert.textContent = _t("⚠ %(product)s (S/N %(serial)s) was sold through %(distributor)s.", {
            product: result.product_name,
            serial: result.serial_no,
            distributor: result.distributor,
        });
    } else if (result.verified) {
        alert.className = "alert alert-success mb-0";
        const title = document.createElement("strong");
        title.textContent = _t("Verified: %(product)s (S/N %(serial)s)", {
            product: result.product_name,
            serial: result.serial_no,
        });
        alert.append(title);
        const details = [
            [_t("Delivered on"), result.delivery_date],
            [_t("Last RMA"), result.last_rma],
        ].filter(([, value]) => value);
        if (details.length) {
            const list = document.createElement("div");
            list.className = "small mt-1";
            list.textContent = details.map(([label, value]) => `${label}: ${value}`).join(" · ");
            alert.append(list);
        }
    } else {
        alert.className = "alert alert-danger mb-0";
        alert.textContent = result.message || _t("Device verification failed.");
    }
    container.append(alert);
}

/** Standalone verification tool (/my/verify). */
publicWidget.registry.SafexVerifyTool = publicWidget.Widget.extend({
    selector: ".o_safex_verify_tool",
    events: {
        "click .o_safex_verify_btn": "_onVerify",
    },

    async _onVerify(ev) {
        ev.preventDefault();
        const serial = this.el.querySelector("#safex_verify_serial").value.trim();
        const imei = this.el.querySelector("#safex_verify_imei").value.trim();
        const result = await verifyDevice(serial, imei);
        renderResult(this.el.querySelector(".o_safex_verify_result"), result);
    },
});

/** Multi-device RMA form (/my/rma/new): each device is verified before it is added. */
publicWidget.registry.SafexRmaNewForm = publicWidget.Widget.extend({
    selector: ".o_safex_rma_new_form",
    events: {
        "click .o_safex_add_device": "_onAddDevice",
        submit: "_onSubmit",
        "click .o_safex_device_rows": "_onRowsClick",
        "change .o_safex_device_rows": "_onRowsChange",
    },

    start() {
        this.nextIndex = 0;
        this.rows = this.el.querySelector(".o_safex_device_rows");
        this.template = this.el.querySelector(".o_safex_device_template");
        this.submitButton = this.el.querySelector(".o_safex_submit_rma");
        this.resultEl = this.el.querySelector(".o_safex_verify_result");
        this._restoreDevices();
        return this._super(...arguments);
    },

    /** After a refused submission the server sends back the devices entered: show them again. */
    _restoreDevices() {
        let devices = [];
        try {
            devices = JSON.parse(this.el.dataset.safexDevices || "[]");
        } catch {
            return;
        }
        for (const device of devices) {
            const card = this._addRow(
                device.serial, device.imei, device.product_name,
                device.other_dealer_confirmed ? device.distributor : ""
            );
            for (const input of card.querySelectorAll("[data-name]")) {
                const name = input.dataset.name;
                if (["serial", "imei", "photos"].includes(name) || !(name in device)) {
                    continue;
                }
                if (input.type === "checkbox") {
                    input.checked = Boolean(device[name]);
                    const block = card.querySelector(`.o_safex_acc_sno[data-accessory="${name}"]`);
                    if (block) {
                        block.classList.toggle("d-none", !input.checked);
                        block.querySelector("input").required = input.checked;
                    }
                } else {
                    input.value = device[name] || "";
                }
            }
        }
    },

    async _onAddDevice(ev) {
        ev.preventDefault();
        // One device at a time: no second lookup / add while one is checked or its popup is open.
        if (this.adding) {
            return;
        }
        this.adding = true;
        let popupOpen = false;
        try {
            popupOpen = await this._verifyAndAdd();
        } finally {
            if (!popupOpen) {
                this.adding = false;
            }
        }
    },

    /** Returns true when the "sold through another dealer" popup was opened (it ends the add itself). */
    async _verifyAndAdd() {
        const serialInput = this.el.querySelector("#safex_new_serial");
        const imeiInput = this.el.querySelector("#safex_new_imei");
        const serial = serialInput.value.trim();
        const imei = imeiInput.value.trim();
        const result = await verifyDevice(serial, imei);
        if (result.verified && this._hasDevice(result.serial_no)) {
            renderResult(this.resultEl, { verified: false, message: _t("This device is already in the RMA.") });
            return false;
        }
        renderResult(this.resultEl, result);
        if (!result.verified) {
            return false;
        }
        const add = () => {
            // The device's own serial is submitted, whatever identifier the dealer typed.
            this._addRow(
                result.serial_no, imei, result.product_name,
                result.status === "other_dealer" ? result.distributor : ""
            );
            serialInput.value = "";
            imeiInput.value = "";
            if (result.status === "other_dealer") {
                this.resultEl.replaceChildren(); // the card shows the "Sold through" badge
            }
        };
        if (result.status !== "other_dealer") {
            add();
            return false;
        }
        // CR-04: device sold through another dealer: the dealer may still raise an RMA for it.
        this.call("dialog", "add", ConfirmationDialog, {
            title: _t("Device sold through another dealer"),
            body: _t("⚠ This device was sold through %(distributor)s. You can still raise an RMA for it.", {
                distributor: result.distributor,
            }),
            confirmLabel: _t("Proceed to RMA"),
            cancelLabel: _t("Cancel"),
            confirm: add,
            cancel: () => {},
        }, {
            onClose: () => {
                this.adding = false;
            },
        });
        return true;
    },

    _hasDevice(serial) {
        return [...this.rows.querySelectorAll(".o_safex_device_card")].some((card) => card.dataset.serial === serial);
    },

    /** The form is sent once: the button is disabled while the RMA is created. */
    _onSubmit() {
        this.submitButton.disabled = true;
    },

    /** otherDealer: name of the dealer the device was sold through, once the dealer confirmed it. */
    _addRow(serial, imei, productName, otherDealer = "") {
        const idx = this.nextIndex++;
        const card = this.template.firstElementChild.cloneNode(true);
        card.dataset.serial = serial;
        card.querySelector(".o_safex_device_title").textContent = productName ? `${productName} - ${serial}` : serial;
        card.querySelector(".o_safex_index").value = idx;
        for (const input of card.querySelectorAll("[data-name]")) {
            input.name = `${input.dataset.name}_${idx}`;
            if (input.dataset.required) {
                input.required = true;
            }
        }
        card.querySelector('[data-name="serial"]').value = serial;
        card.querySelector('[data-name="imei"]').value = imei;
        card.querySelector('[data-name="other_dealer_confirmed"]').value = otherDealer ? "1" : "";
        if (otherDealer) {
            const badge = card.querySelector(".o_safex_other_dealer_badge");
            badge.textContent = _t("Sold through %(distributor)s", { distributor: otherDealer });
            badge.classList.remove("d-none");
        }
        this.rows.append(card);
        this._updateSubmit();
        return card;
    },

    _onRowsClick(ev) {
        const removeButton = ev.target.closest(".o_safex_remove_device");
        if (removeButton) {
            removeButton.closest(".o_safex_device_card").remove();
            this._updateSubmit();
        }
    },

    /** Ticking Battery / Docking Station asks its serial number in a pop-up, verified at once: the
     *  accessory stays ticked only with a verified serial number (shown read-only on the card). */
    _onRowsChange(ev) {
        const checkbox = ev.target;
        if (checkbox.type !== "checkbox") {
            return;
        }
        const card = checkbox.closest(".o_safex_device_card");
        const block = card.querySelector(`.o_safex_acc_sno[data-accessory="${checkbox.dataset.name}"]`);
        const texts = ACCESSORY_TEXTS[checkbox.dataset.name];
        if (!block || !texts) {
            return;
        }
        const input = block.querySelector("input");
        const setSerial = (serial) => {
            input.value = serial;
            checkbox.checked = Boolean(serial);
            block.classList.toggle("d-none", !serial);
            input.required = Boolean(serial);
        };
        if (!checkbox.checked) {
            setSerial("");
            return;
        }
        checkbox.checked = false; // ticked again once the serial number is verified
        let verified = false;
        this.call("dialog", "add", AccessorySerialDialog, {
            kind: texts.kind,
            title: texts.title,
            label: texts.label,
            placeholder: texts.placeholder,
            serial: input.value,
            onVerified: (serial) => {
                verified = true;
                setSerial(serial);
            },
        }, {
            onClose: () => {
                if (!verified) {
                    setSerial("");
                }
            },
        });
    },

    _updateSubmit() {
        this.submitButton.disabled = !this.rows.querySelector(".o_safex_device_card");
    },
});
