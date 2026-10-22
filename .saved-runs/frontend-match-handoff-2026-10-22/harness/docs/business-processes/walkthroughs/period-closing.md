# Period Closing

Source: [Marble ERP User Guide/Accounting/Period Closing](https://moqui.org/docs/apps/Marble%20ERP%20User%20Guide/Accounting/Period%20Closing)

Type: UI walkthrough.

## Fiscal Time Periods
By default the system tracks yearly, quarterly, and monthly fiscal periods. Monthly periods are children of quarterly periods, and quarterly periods children of yearly. Period numbers mean different things for each. For yearly periods the period number is just the year. Quarterly and monthly period numbers are the number within the year. Each period also has a reference to the previous period.
- visual test:
- transition test:

These periods can be the same as or different from calendar periods; in other words a fiscal year may or may not match the calendar year by its from and thru dates. Periods are 'owned' by a specific internal organization in the system so different organizations may have different periods. The system will automatically create current and next periods as needed over time, or they can be generated well in advance by starting with a manually created period and then using the button on the *Accounting* => *Time Periods* screen to create the next period.
- visual test:
- transition test:

There is also an internal service (not exposed in the standard user interface) that can be used by a developer or system administrator to create bulk periods going as far back in time as needed. This is mostly used for initial system setup when transactional data going into the past is imported or migrated from another system.
- visual test:
- transition test:

### Find and Manage Periods

TODO
- visual test:
- transition test:

### View GL Account Summary for Period

TODO
- visual test:
- transition test:

## When and How to Close
Closing a period prevents transactions with a date within that period from being posted. The main exception to this is that accounting transactions with the types **Period Closing Adjustment** (for manual adjustments) and **Net Income Period Closing** (for net income booking) may be posted to a closed period. A user with a special permission may also 'force post' to a closed period, and this must be done explicitly with the **Force Post** button on the *Edit Transaction* screen.
- visual test:
- transition test:

GL transactions are typically created and posted automatically based on invoices, payments, asset receipt and issuance, financial (single entry balance) account deposits and withdrawals, and so on. Transactions may also be created manually. However they are created and posted if there are any issues with the transaction, including a period covering the date of the transaction being closed, the transaction will automatically be added to the Error Journal configured for the organization and will be left unposted. When you try to close a period it will make sure there are no unposted transactions with a date within the period.
- visual test:
- transition test:

Period closing is a tool that a CFO, controller, or other senior accountant can use to stabilize the books for more official reporting. If a bookkeeper or other user records an invoice or any other transactional record that results in a GL transaction and it has a date in a closed period then it will be added to the error journal instead of posting as described above. A more senior accountant responsible for financial reporting can then review that transaction and decide whether the date on the transaction should be changed, or it is a case where it does need to be posted in a closed period along with the business implications involved.
- visual test:
- transition test:

How often or frequently you choose to close periods is mostly based on organization requirements. In some organizations yearly closing is adequate to stabilize books for tax reporting and reporting to investors and creditors. In other organizations quarterly closing is required. It is not as common that monthly closing is required but for faster paced organizations or if you just want to run a tighter ship this is supported.
- visual test:
- transition test:

To close a period all periods it depends on must be closed, including prior and child periods. For example to close a year the prior year must be closed and all quarters in the year must be closed, and for each quarter to be closed all months within the quarter must be closed. In other words when closing periods start with months, then close quarters once all months in the quarter are closed, then close a year once all quarters in the year are closed. Periods may be closed one at a time using the **Close Period** button on the *Accounts* tab of the *Accounting* => *Time Period* screen.  For convenience a period and all prior and child periods can be closed all at once using the **Close Period + Depends** button.
- visual test:
- transition test:

There are typically various business activities that lead up to period closing including reviewing and clearing the error journal, reconciliation with invoices (see the *Invoice Reconciliation* report), bank account reconciliation, fixed asset depreciation, and so on.
- visual test:
- transition test:

### Review Error Journal

TODO
- visual test:
- transition test:

### Invoice Reconciliation

TODO
- visual test:
- transition test:

### Bank Account Reconciliation

TODO
- visual test:
- transition test:

### Calculate and Post Depreciation

TODO
- visual test:
- transition test:

### Close a Period

TODO
- visual test:
- transition test:

## Net Income Closing Transactions
Balances from income statement accounts can be posted to the Net Income account (in the default chart of accounts 850000000) using the GL transaction type **Net Income Period Closing**. This type of transaction can be posted at any time, even after the period is closed. Posting these transactions after a period is closed is generally best to avoid GL account balance changes that modify the income statement amounts that need to be booked. 
- visual test:
- transition test:

These transactions are handled differently from other transactions and do not modify the amounts shown on the **Income Statement** report. These transactions do have an effect on the **Balance Sheet** report. If you look at the Balance Sheet for a period before posting the net income closing transactions you'll see the amount not yet booked in the **Unbooked Net Income** line. Once all income has been booked for the period this line should show a zero amount.
- visual test:
- transition test:

While net income closing transactions can be created and posted manually the system can do this automatically for you with the **Net Income Closing Transactions** form on the **Accounts** tab of the **Time Period** screen. This looks at the ending balance (including 'Net Income Period Closing' type transactions already posted) of each income statement account and uses that amount to zero out each account as of the end of the period you run it for. When you run this you can choose whether to post transactions or not (if not posted they will be generated and left unposted), specify an optional journal to add the transactions to for tracking, and which GL account to post it to (if there are multiple Net Income accounts, or you want to post it directly to a retained earnings account).
- visual test:
- transition test:

When the automatic Net Income Closing Transactions are run it will create a GL transaction for each GL Account Class on the income statement with a transaction entry for each income statement GL account and a balancing entry for the selected Net Income or other GL account to book the income to.
- visual test:
- transition test:

To see what has already been posted to the Net Income account over time you can use the **Account Balance History** report. The **Find Options** to use to narrow the results are typically the *Period Type*, the *Organization*, and the *GL Account* (like the 850000000 Net Income account).
- visual test:
- transition test:

On the **Accounts** tab of the **Time Period** screen you can also see a summary of GL account balances for the period.  The **Ending** column shows the ending balance. Before running Net Income Closing Transactions the ending balance for income statement accounts will be the amount that needs to be booked, and after running it the ending balance in that table should be 0.00 for all income statement accounts.
- visual test:
- transition test:

While you can book directly to a retained earnings account it is generally the better practice to book to the Net Income account, and then do manual transactions to distribute the Net Income balance to the retained earnings or other desired equity accounts. When doing this use the **Period Closing Adjustment** transaction type. This helps keep track of these and similar transactions and allows them to be posted in closed periods.
- visual test:
- transition test:

### View Unbooked Net Income

TODO
- visual test:
- transition test:

### Automatic Net Income Closing Transactions

TODO: use 'Net Income Closing Transactions' form, view results on Account Ledger report for the period and the target account (ie 850000000)
- visual test:
- transition test:

### Manual Transaction for Equity Allocation

TODO
- visual test:
- transition test:
