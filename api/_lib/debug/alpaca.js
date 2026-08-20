'use strict';
/* TEMPORARY diagnostic endpoint — REMOVE after feed=iex investigation.
 * POST { "symbol": "AAPL", "feed": "iex" | "sip" } -> raw Alpaca bars probe. */
const { buildHandler } = require('../_debug_alpaca');
module.exports = buildHandler('iex'); // default; feed overridable via body
