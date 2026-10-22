Restore Java Bootstrap form metrics in the apps renderer: 34px controls, 6px/12px control padding, 15px field spacing, 7px label padding, and 34px static/link values. Keep list controls compact and the Java big-row child margin override. Stacked on #49; only CSS and its browser regression change.

Validation: parent independently passed the Chromium geometry test and eight JavaScript tests (9 total); git diff --check passes. The regression covers standard text/select/static/link metrics plus list and big-row spacing. Java references: Bootstrap form-control/form-group/form-horizontal rules and webroot-layout.css lines 64–67, 87, 132–135.

Completed populated EditInvoice capture: .runs/2026-10-20_01-55-59.979813Z. All four Java/Rust apps/qapps captures authenticated without browser errors. Apps differing pixels decreased from 19.5448% to 7.6713%; qapps remained 13.4415%. Screenshot dimensions still differ. Step 4 ran after verified graceful shutdown and failed final database equality (shutdown_verified=true, final_databases_equal=false, passed=false). No approvals changed. This is visual progress, not full screen or workflow parity.

Before (apps):

![Apps before form metrics](https://files.catbox.moe/e3z1w9.png)

After (apps):

![Apps after form metrics](https://files.catbox.moe/ziv9dl.png)
