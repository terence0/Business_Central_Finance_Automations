page 68311 "FYC Close Log API"
{
    PageType = API;
    Caption = 'Fiscal Year Close Log API';
    APIPublisher = 'contoso';
    APIGroup = 'financeautomation';
    APIVersion = 'v1.0';
    EntityName = 'fiscalYearCloseLogEntry';
    EntitySetName = 'fiscalYearCloseLogEntries';
    SourceTable = "FYC Close Log";
    ODataKeyFields = SystemId;
    Editable = false;
    InsertAllowed = false;
    ModifyAllowed = false;
    DeleteAllowed = false;
    DataAccessIntent = ReadOnly;
    Extensible = false;

    layout
    {
        area(Content)
        {
            repeater(Records)
            {
                field(id; Rec.SystemId) { Caption = 'Id'; }
                field(entryNo; Rec."Entry No.") { Caption = 'Entry No.'; }
                field(createdAt; Rec."Created At") { Caption = 'Created At'; }
                field(runId; Rec."Run ID") { Caption = 'Run ID'; }
                field(status; Rec.Status) { Caption = 'Status'; }
                field(logAction; Rec."Log Action") { Caption = 'Action'; }
                field(fiscalYearStart; Rec."Fiscal Year Start") { Caption = 'Fiscal Year Start'; }
                field(fiscalYearEnd; Rec."Fiscal Year End") { Caption = 'Fiscal Year End'; }
                field(documentNo; Rec."Document No.") { Caption = 'Document No.'; }
                field(noOfLines; Rec."No. of Lines") { Caption = 'No. of Lines'; }
                field(retainedEarningsAmount; Rec."Retained Earnings Amount") { Caption = 'Retained Earnings Amount'; }
                field(message; Rec.Message) { Caption = 'Message'; }
                field(userId; Rec."User ID") { Caption = 'User ID'; }
            }
        }
    }
}
