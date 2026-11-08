page 50150 "CON Cost Centre Dimension Values"
{
    PageType = API;
    Caption = 'CON Cost Centre Dimension Values';

    APIPublisher = 'contoso';
    APIGroup = 'financeautomation';
    APIVersion = 'v1.0';

    EntityName = 'costCentreDimensionValue';
    EntitySetName = 'costCentreDimensionValues';

    SourceTable = "Dimension Value";
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

                field(dimensionCode; Rec."Dimension Code")
                {
                    Caption = 'Dimension Code';
                }

                field(code; Rec.Code)
                {
                    Caption = 'Code';
                }

                field(name; Rec.Name)
                {
                    Caption = 'Name';
                }

                field(blocked; Rec.Blocked)
                {
                    Caption = 'Blocked';
                }
            }
        }
    }
}
