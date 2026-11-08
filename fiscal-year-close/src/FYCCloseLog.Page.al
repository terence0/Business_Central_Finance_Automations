page 68301 "FYC Close Log"
{
    Caption = 'Fiscal Year Close Log';
    PageType = List;
    SourceTable = "FYC Close Log";
    SourceTableView = sorting("Entry No.") order(descending);
    UsageCategory = History;
    ApplicationArea = All;
    Editable = false;

    layout
    {
        area(Content)
        {
            repeater(Lines)
            {
                field("Entry No."; Rec."Entry No.") { ApplicationArea = All; ToolTip = 'Specifies the entry number.'; }
                field("Created At"; Rec."Created At") { ApplicationArea = All; ToolTip = 'Specifies when the action happened.'; }
                field(Status; Rec.Status) { ApplicationArea = All; ToolTip = 'Specifies whether the step succeeded, failed, or is for information.'; StyleExpr = StatusStyle; }
                field("Log Action"; Rec."Log Action") { ApplicationArea = All; ToolTip = 'Specifies what the automation did.'; }
                field("Fiscal Year Start"; Rec."Fiscal Year Start") { ApplicationArea = All; ToolTip = 'Specifies the fiscal year start date.'; }
                field("Fiscal Year End"; Rec."Fiscal Year End") { ApplicationArea = All; ToolTip = 'Specifies the fiscal year end date.'; }
                field("Document No."; Rec."Document No.") { ApplicationArea = All; ToolTip = 'Specifies the closing document number.'; }
                field("No. of Lines"; Rec."No. of Lines") { ApplicationArea = All; ToolTip = 'Specifies the number of journal lines or periods created.'; }
                field("Retained Earnings Amount"; Rec."Retained Earnings Amount") { ApplicationArea = All; ToolTip = 'Specifies the amount posted to retained earnings. A negative amount is a profit (credit).'; }
                field(Message; Rec.Message) { ApplicationArea = All; ToolTip = 'Specifies details or the error message.'; }
                field("User ID"; Rec."User ID") { ApplicationArea = All; ToolTip = 'Specifies the user the automation ran as.'; }
                field("Run ID"; Rec."Run ID") { ApplicationArea = All; ToolTip = 'Specifies the run the entry belongs to. All steps of one run share it.'; Visible = false; }
            }
        }
    }

    var
        StatusStyle: Text;

    trigger OnAfterGetRecord()
    begin
        case Rec.Status of
            Rec.Status::Success:
                StatusStyle := 'Favorable';
            Rec.Status::Failed:
                StatusStyle := 'Unfavorable';
            else
                StatusStyle := 'Standard';
        end;
    end;
}
