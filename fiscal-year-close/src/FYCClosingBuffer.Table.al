table 68302 "FYC Closing Buffer"
{
    Caption = 'Fiscal Year Closing Buffer';
    TableType = Temporary;
    DataClassification = SystemMetadata;

    fields
    {
        field(1; "G/L Account No."; Code[20]) { Caption = 'G/L Account No.'; }
        field(2; "Business Unit Code"; Code[20]) { Caption = 'Business Unit Code'; }
        field(3; "Global Dimension 1 Code"; Code[20]) { Caption = 'Global Dimension 1 Code'; }
        field(4; "Global Dimension 2 Code"; Code[20]) { Caption = 'Global Dimension 2 Code'; }
        field(10; Amount; Decimal) { Caption = 'Amount'; }
        field(11; "Additional-Currency Amount"; Decimal) { Caption = 'Additional-Currency Amount'; }
    }

    keys
    {
        key(PK; "G/L Account No.", "Business Unit Code", "Global Dimension 1 Code", "Global Dimension 2 Code") { Clustered = true; }
    }
}
