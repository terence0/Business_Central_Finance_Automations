page 50100 "CON GL Setup API"
{
    PageType = API;
    Caption = 'CON GL Setup API';

    APIPublisher = 'contoso';
    APIGroup = 'financeautomation';
    APIVersion = 'v1.0';

    EntityName = 'glSetup';
    EntitySetName = 'glSetups';

    SourceTable = "General Ledger Setup";
    ODataKeyFields = SystemId;

    InsertAllowed = false;
    DeleteAllowed = false;
    ModifyAllowed = true;
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

                field(allowPostingFrom; Rec."Allow Posting From")
                {
                    Caption = 'Allow Posting From';
                }

                field(allowPostingTo; Rec."Allow Posting To")
                {
                    Caption = 'Allow Posting To';
                }

                field(lastModifiedDateTime; Rec.SystemModifiedAt)
                {
                    Caption = 'Last Modified Date Time';
                    Editable = false;
                }
            }
        }
    }
}