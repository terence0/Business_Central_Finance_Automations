table 68301 "FYC Close Log"
{
    Caption = 'Fiscal Year Close Log';
    DataClassification = CustomerContent;
    LookupPageId = "FYC Close Log";
    DrillDownPageId = "FYC Close Log";

    fields
    {
        field(1; "Entry No."; Integer)
        {
            Caption = 'Entry No.';
            AutoIncrement = true;
        }
        field(2; "Created At"; DateTime)
        {
            Caption = 'Created At';
        }
        field(3; "Log Action"; Enum "FYC Log Action")
        {
            Caption = 'Action';
        }
        field(4; "Fiscal Year Start"; Date)
        {
            Caption = 'Fiscal Year Start';
        }
        field(5; "Fiscal Year End"; Date)
        {
            Caption = 'Fiscal Year End';
        }
        field(6; "Document No."; Code[20])
        {
            Caption = 'Document No.';
        }
        field(7; "No. of Lines"; Integer)
        {
            Caption = 'No. of Lines';
        }
        field(8; "Retained Earnings Amount"; Decimal)
        {
            Caption = 'Retained Earnings Amount';
            AutoFormatType = 1;
        }
        field(9; "Message"; Text[2048])
        {
            Caption = 'Message';
        }
        field(10; "User ID"; Code[50])
        {
            Caption = 'User ID';
            DataClassification = EndUserIdentifiableInformation;
        }
        field(11; Status; Enum "FYC Log Status")
        {
            Caption = 'Status';
        }
        field(12; "Run ID"; Guid)
        {
            Caption = 'Run ID';
        }
    }

    keys
    {
        key(PK; "Entry No.") { Clustered = true; }
    }
}
