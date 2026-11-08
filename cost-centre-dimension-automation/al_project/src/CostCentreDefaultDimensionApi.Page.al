page 50151 "CON Cost Centre Default Dim"
{
    PageType = API;
    Caption = 'CON Cost Centre Default Dimensions';

    APIPublisher = 'contoso';
    APIGroup = 'financeautomation';
    APIVersion = 'v1.0';

    EntityName = 'costCentreDefaultDimension';
    EntitySetName = 'costCentreDefaultDimensions';

    SourceTable = "Default Dimension";
    ODataKeyFields = SystemId;

    InsertAllowed = true;
    ModifyAllowed = true;
    DeleteAllowed = false;
    DelayedInsert = false;

    layout
    {
        area(Content)
        {
            repeater(Group)
            {
                field(id; Rec.SystemId)
                {
                    Caption = 'Id';
                    Editable = false;
                }

                field(tableId; Rec."Table ID")
                {
                    Caption = 'Table ID';
                }

                field(no; Rec."No.")
                {
                    Caption = 'No.';
                }

                field(dimensionCode; Rec."Dimension Code")
                {
                    Caption = 'Dimension Code';
                }

                field(dimensionValueCode; Rec."Dimension Value Code")
                {
                    Caption = 'Dimension Value Code';
                }

                field(valuePosting; Rec."Value Posting")
                {
                    Caption = 'Value Posting';
                }
            }
        }
    }
}
