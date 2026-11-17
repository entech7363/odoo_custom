import { patch } from "@web/core/utils/patch";
import { FormCompiler } from "@web/views/form/form_compiler";

/**
 * SafeX RMA / RMA device forms: a notebook with class "o_safex_stage_notebook" opens the page whose
 * name is in the record's "safex_stage_page" field (the page to fill in at the current stage). The
 * user can still switch pages; the stage page is opened again when the stage changes.
 */
patch(FormCompiler.prototype, {
    compileNotebook(el, params) {
        const isStageNotebook = (el.getAttribute("class") || "").split(/\s+/).includes("o_safex_stage_notebook");
        const noteBook = super.compileNotebook(el, params);
        if (!isStageNotebook) {
            return noteBook;
        }
        const pageIds = {};
        for (const slot of noteBook.children) {
            const slotId = slot.getAttribute("t-set-slot");
            const name = (slot.getAttribute("name") || "").replace(/^[`'"]|[`'"]$/g, "");
            if (slotId && name) {
                pageIds[name] = slotId;
            }
        }
        const fallback = noteBook.getAttribute("defaultPage") || "undefined";
        noteBook.setAttribute(
            "defaultPage",
            `(${JSON.stringify(pageIds)})[__comp__.props.record.data.safex_stage_page] || (${fallback})`
        );
        return noteBook;
    },
});
