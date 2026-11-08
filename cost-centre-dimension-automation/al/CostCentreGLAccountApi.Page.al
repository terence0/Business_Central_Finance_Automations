page 50112 "CON Cost Centre GL Accounts"
{
    PageType = API;
    Caption = 'CON Cost Centre G/L Accounts';

    APIPublisher = 'contoso';
    APIGroup = 'financeautomation';
    APIVersion = 'v1.0';

    EntityName = 'costCentreGLAccount';
    EntitySetName = 'costCentreGLAccounts';

    SourceTable = "G/L Account";
    ODataKeyFields = SystemId;

    InsertAllowed = false;
    ModifyAllowed = false;
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

                field(no; Rec."No.")
                {
                    Caption = 'No.';
                }

                field(name; Rec.Name)
                {
                    Caption = 'Name';
                }

                field(accountType; Rec."Account Type")
                {
                    Caption = 'Account Type';
                }

                field(blocked; Rec.Blocked)
                {
                    Caption = 'Blocked';
                }
            }
        }
    }
}
