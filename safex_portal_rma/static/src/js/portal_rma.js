import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";

async function verifyDevice(serialNo, imei) {
    return rpc("/my/rma/verify_device", { serial_no: serialNo, imei: imei });
}

function renderResult(container, result) {
    container.replaceChildren();
    const alert = document.createElement("div");
    alert.setAttribute("role", "alert");
    if (result.verified) {
        alert.className = "alert alert-success mb-0";
        alert.textContent = _t("Verified: %s", result.product_name);
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
        "click .o_safex_device_rows": "_onRowsClick",
    },

    start() {
        this.nextIndex = 0;
        this.rows = this.el.querySelector(".o_safex_device_rows");
        this.template = this.el.querySelector(".o_safex_device_template");
        this.submitButton = this.el.querySelector(".o_safex_submit_rma");
        this.resultEl = this.el.querySelector(".o_safex_verify_result");
        return this._super(...arguments);
    },

    async _onAddDevice(ev) {
        ev.preventDefault();
        const serialInput = this.el.querySelector("#safex_new_serial");
        const imeiInput = this.el.querySelector("#safex_new_imei");
        const serial = serialInput.value.trim();
        const imei = imeiInput.value.trim();
        const alreadyAdded = [...this.rows.querySelectorAll('[data-name="serial"]')].some(
            (input) => input.value === serial
        );
        if (alreadyAdded) {
            renderResult(this.resultEl, { verified: false, message: _t("This device is already in the RMA.") });
            return;
        }
        const result = await verifyDevice(serial, imei);
        renderResult(this.resultEl, result);
        if (!result.verified) {
            return;
        }
        this._addRow(serial, imei, result.product_name);
        serialInput.value = "";
        imeiInput.value = "";
    },

    _addRow(serial, imei, productName) {
        const idx = this.nextIndex++;
        const card = this.template.firstElementChild.cloneNode(true);
        card.querySelector(".o_safex_device_title").textContent = `${productName} - ${serial}`;
        card.querySelector(".o_safex_index").value = idx;
        for (const input of card.querySelectorAll("[data-name]")) {
            input.name = `${input.dataset.name}_${idx}`;
            if (input.dataset.required) {
                input.required = true;
            }
        }
        card.querySelector('[data-name="serial"]').value = serial;
        card.querySelector('[data-name="imei"]').value = imei;
        this.rows.append(card);
        this._updateSubmit();
    },

    _onRowsClick(ev) {
        const removeButton = ev.target.closest(".o_safex_remove_device");
        if (removeButton) {
            removeButton.closest(".o_safex_device_card").remove();
            this._updateSubmit();
        }
    },

    _updateSubmit() {
        this.submitButton.disabled = !this.rows.querySelector(".o_safex_device_card");
    },
});
