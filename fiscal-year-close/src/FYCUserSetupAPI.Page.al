page 68312 "FYC User Setup API"
{
    // Lets the Streamlit control panel read and set users' allowed posting dates in every
    // company. Only the user and the two posting date fields are exposed.
    PageType = API;
    Caption = 'Fiscal Year Close User Posting Dates API';
    APIPublisher = 'contoso';
    APIGroup = 'financeautomation';
    APIVersion = 'v1.0';
    EntityName = 'userPostingDate';
    EntitySetName = 'userPostingDates';
    SourceTable = "User Setup";
    ODataKeyFields = SystemId;
    DelayedInsert = true;
    InsertAllowed = true;
    ModifyAllowed = true;
    DeleteAllowed = false;
    Extensible = false;
    Permissions = tabledata "User Setup" = rim;

    layout
    {
        area(Content)
        {
            repeater(Records)
            {
                field(id; Rec.SystemId) { Caption = 'Id'; Editable = false; }
                field(userId; Rec."User ID") { Caption = 'User ID'; }
                field(allowPostingFrom; Rec."Allow Posting From") { Caption = 'Allow Posting From'; }
                field(allowPostingTo; Rec."Allow Posting To") { Caption = 'Allow Posting To'; }
                field(isCurrentUser; IsCurrentUser) { Caption = 'Is Current User'; Editable = false; }
            }
        }
    }

    var
        IsCurrentUser: Boolean;

    trigger OnAfterGetRecord()
    begin
        IsCurrentUser := Rec."User ID" = UpperCase(UserId());
    end;
}
