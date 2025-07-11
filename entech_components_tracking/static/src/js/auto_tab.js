odoo.define('entech_components_tracking.auto_tab_serial', function (require) {
    "use strict";

    const fieldRegistry = require('web.field_registry');
    const AbstractField = require('web.AbstractField');

    const AutoTabSerial = AbstractField.extend({
        events: {
            keydown: '_onKeydown',
        },

        _onKeydown: function (ev) {
            if (ev.key === 'Enter' || ev.keyCode === 13) {
                ev.preventDefault();
                // Get all input fields in the form
                const inputs = this.el.closest('form').querySelectorAll('input');
                const index = Array.prototype.indexOf.call(inputs, this.el);
                if (index >= 0 && index < inputs.length - 1) {
                    inputs[index + 1].focus();
                }
            }
        },
    });

    fieldRegistry.add('auto_tab_serial', AutoTabSerial);
});
