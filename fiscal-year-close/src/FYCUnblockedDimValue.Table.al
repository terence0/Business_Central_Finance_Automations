table 68303 "FYC Unblocked Dim. Value"
{
    // Dimension values the posting window unblocked so the closing journal could post.
    // Kept until they are blocked again, so an interrupted run is restored by the next one.
    Caption = 'Fiscal Year Close Unblocked Dimension Value';
    DataClassification = CustomerContent;

    fields
    {
        field(1; "Dimension Code"; Code[20])
        {
            Caption = 'Dimension Code';
        }
        field(2; "Dimension Value Code"; Code[20])
        {
            Caption = 'Dimension Value Code';
        }
    }

    keys
    {
        key(PK; "Dimension Code", "Dimension Value Code") { Clustered = true; }
    }
}
