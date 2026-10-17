# OAGIS Work Plan to Cash

Source: [Business Process Library/OAGIS Work Plan to Cash](https://moqui.org/docs/mantle/Business%20Process%20Library/OAGIS%20Work%20Plan%20to%20Cash)

Type: Business-process description; verify UI applicability.

NOTE: These pages describe OAGIS document-exchange scenarios. The `mantle-oagis` component is listed in addons.xml with no releases and is not required to run Moqui, Mantle USL, or Marble ERP.
- visual test:
- transition test:

## Introduction

This process covers project work including billable time and expenses. OAGIS doesn't have many scenarios to cover this literally, so it is mostly an adaptation of similar manufacturing scenarios.
- visual test:
- transition test:

## OAGIS Scenarios

* 9 - Project Accounting Synchronization
  - visual test:
  - transition test:
* 10 - Feeder Applications to Project Accounting
  - visual test:
  - transition test:
* 11 - Human Resources to Manufacturing
  - visual test:
  - transition test:
* 20 - Plant Data Collection / Warehouse Management / Time and Attendance
  - visual test:
  - transition test:
* 32 - Human Resources Integration to Manufacturing
  - visual test:
  - transition test:
* 33 - Human Resources to Time Data Collection
  - visual test:
  - transition test:

## Actors

TODO
- visual test:
- transition test:

## Process Story

Budget, Accounts Receivable, Order Management, Purchasing, Accounts Payable, Time and Labor, and Travel and Expenses send PostProjectAccounting to Project Accounting then Project Accounting sends back ConfirmBOD.
Project Accounting sends SyncProjectMaster to Budget, Accounts Receivable, Order Management, Purchasing, Accounts Payable, Time and Labor, and/or Travel and Expenses then each sends ConfirmBOD to Project Accounting.
- visual test:
- transition test:

Human Resources sends SyncPersonnel to Work Planning and Work Planning sends ConfirmBOD to HR.
Human Resources sends SyncEmployeeWorkSchedule to Work Planning and Work Planning sends ConfirmBOD to HR.
Work Planning sends SyncField to HR and HR sends ConfirmBOD to Work Planning.
- visual test:
- transition test:

Time Collection sends GetPersonnel to Work Planning and Work Planning sends ShowPersonnel to Time Collection.
Time Collection sends UpdateEmployeeWorkTime to Work Planning and Work Planning sends RespondEmployeeWorkTime to Time Collection.
- visual test:
- transition test:

HR pays worker. HR sends PostJournalEntry to GL and GL sends PostAcknowledgeJournalEntry to HR.
- visual test:
- transition test:

## OAGIS Documents Used

* PostProjectAccounting - ConfirmBOD
  - visual test:
  - transition test:
* SyncProjectMaster - ConfirmBOD
  - visual test:
  - transition test:

* SyncPersonnel - ConfirmBOD
  - visual test:
  - transition test:
* SyncEmployeeWorkSchedule - ConfirmBOD
  - visual test:
  - transition test:
* SyncField - ConfirmBOD
  - visual test:
  - transition test:
* GetPersonnel - ShowPersonnel
  - visual test:
  - transition test:
* UpdateEmployeeWorkTime - RespondEmployeeWorkTime
  - visual test:
  - transition test:

* PostJournalEntry - PostAcknowledgeJournalEntry
  - visual test:
  - transition test:
