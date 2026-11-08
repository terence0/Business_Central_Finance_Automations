table 68304 "FYC Relaxed Default Dim."
{
    // Default dimension posting rules the posting window lifted so the closing journal could post.
    // Kept until they are put back, so an interrupted run is restored by the next one.
    Caption = 'Fiscal Year Close Relaxed Default Dimension';
    DataClassification = CustomerContent;

    fields
    {
        field(1; "Table ID"; Integer)
        {
            Caption = 'Table ID';
        }
        field(2; "No."; Code[20])
        {
            Caption = 'No.';
        }
        field(3; "Dimension Code"; Code[20])
        {
            Caption = 'Dimension Code';
        }
        field(4; "Value Posting"; Enum "Default Dimension Value Posting Type")
        {
            Caption = 'Value Posting';
        }
    }

    keys
    {
        key(PK; "Table ID", "No.", "Dimension Code") { Clustered = true; }
    }
}
