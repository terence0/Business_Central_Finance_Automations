page 68217 "CON User Permission Sets"
{
    PageType = List;
    ApplicationArea = All;
    UsageCategory = Administration;
    Caption = 'User Permission Sets';
    SourceTable = "Access Control";
    Editable = false;

    layout
    {
        area(Content)
        {
            repeater(Assignments)
            {
                field(user; Rec."User Name")
                {
                    ApplicationArea = All;
                    Caption = 'User';
                }

                field(userSecurityId; Rec."User Security ID")
                {
                    ApplicationArea = All;
                    Caption = 'User Security ID';
                }

                field(permissionSet; Rec."Role ID")
                {
                    ApplicationArea = All;
                    Caption = 'Permission Set';
                }

                field(company; Rec."Company Name")
                {
                    ApplicationArea = All;
                    Caption = 'Company';
                }

                field(appName; Rec."App Name")
                {
                    ApplicationArea = All;
                    Caption = 'App Name';
                }

                field(scope; Rec.Scope)
                {
                    ApplicationArea = All;
                    Caption = 'Scope';
                }
            }
        }
    }
}
