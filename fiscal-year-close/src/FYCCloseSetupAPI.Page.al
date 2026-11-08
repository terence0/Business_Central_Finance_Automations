page 68310 "FYC Close Setup API"
{
    // Exposes the per-company setup and the run actions, so an external app
    // (the Streamlit control panel) can manage every company from one place.
    PageType = API;
    Caption = 'Fiscal Year Close Setup API';
    APIPublisher = 'contoso';
    APIGroup = 'financeautomation';
    APIVersion = 'v1.0';
    EntityName = 'fiscalYearCloseSetup';
    EntitySetName = 'fiscalYearCloseSetups';
    SourceTable = "FYC Close Setup";
    ODataKeyFields = SystemId;
    DelayedInsert = true;
    InsertAllowed = true;
    ModifyAllowed = true;
    DeleteAllowed = false;
    Extensible = false;

    layout
    {
        area(Content)
        {
            repeater(Records)
            {
                field(id; Rec.SystemId) { Caption = 'Id'; Editable = false; }
                field(enabled; Rec.Enabled) { Caption = 'Enabled'; }
                field(closeDelayDays; Rec."Close Delay (Days)") { Caption = 'Close Delay (Days)'; }
                field(earliestFiscalYearStart; Rec."Earliest Fiscal Year Start") { Caption = 'Earliest Fiscal Year Start'; }
                field(recloseLookbackYears; Rec."Re-close Lookback (Years)") { Caption = 'Re-close Lookback (Years)'; }
                field(autoCreateNextFiscalYear; Rec."Auto-Create Next Fiscal Year") { Caption = 'Auto-Create Next Fiscal Year'; }
                field(periodLength; PeriodLengthTxt)
                {
                    Caption = 'Period Length';

                    trigger OnValidate()
                    begin
                        Evaluate(Rec."Period Length", PeriodLengthTxt);
                    end;
                }
                field(noOfPeriods; Rec."No. of Periods") { Caption = 'No. of Periods'; }
                field(journalTemplateName; Rec."Gen. Journal Template Name") { Caption = 'Gen. Journal Template Name'; }
                field(journalBatchName; Rec."Gen. Journal Batch Name") { Caption = 'Gen. Journal Batch Name'; }
                field(retainedEarningsAccount; Rec."Retained Earnings Acc.") { Caption = 'Retained Earnings Acc.'; }
                field(documentNoPrefix; Rec."Document No. Prefix") { Caption = 'Document No. Prefix'; }
                field(postingDescription; Rec."Posting Description") { Caption = 'Posting Description'; }
                field(closeByBusinessUnit; Rec."Close by Business Unit") { Caption = 'Close by Business Unit'; }
                field(closeByGlobalDimension1; Rec."Close by Global Dimension 1") { Caption = 'Close by Global Dimension 1'; }
                field(closeByGlobalDimension2; Rec."Close by Global Dimension 2") { Caption = 'Close by Global Dimension 2'; }
                field(postAutomatically; Rec."Post Automatically") { Caption = 'Post Automatically'; }
                field(jobQueueEntryExists; JobQueueEntryExists) { Caption = 'Job Queue Entry Exists'; Editable = false; }
                field(openPostingWindow; Rec."Open Posting Window") { Caption = 'Open Posting Window'; }
                field(postingWindowUser; Rec."Window User ID") { Caption = 'Posting Window Open For'; Editable = false; }
                field(postingWindowOpenedAt; Rec."Window Opened At") { Caption = 'Posting Window Opened At'; Editable = false; }
                field(currentUserId; CurrentUserId) { Caption = 'Current User ID'; Editable = false; }
                field(targetFiscalYearEnd; Rec."Target Fiscal Year End") { Caption = 'Target Fiscal Year End'; }
            }
        }
    }

    var
        PeriodLengthTxt: Text[30];
        JobQueueEntryExists: Boolean;
        CurrentUserId: Code[50];

    trigger OnNewRecord(BelowxRec: Boolean)
    begin
        Evaluate(Rec."Period Length", '<1M>');
        PeriodLengthTxt := Format(Rec."Period Length");
    end;

    trigger OnAfterGetRecord()
    var
        JobQueueHandler: Codeunit "FYC Job Queue Handler";
    begin
        PeriodLengthTxt := Format(Rec."Period Length");
        JobQueueEntryExists := JobQueueHandler.JobQueueEntryExists();
        // The user the API runs as, so the app knows whose posting dates the close depends on.
        CurrentUserId := CopyStr(UserId(), 1, MaxStrLen(CurrentUserId));
    end;

    /// <summary>Runs the full automation now: closes due fiscal years and runs Close Income Statement.</summary>
    [ServiceEnabled]
    procedure runNow(var ActionContext: WebServiceActionContext)
    var
        Runner: Codeunit "FYC Close Runner";
    begin
        Runner.Execute("FYC Run Mode"::"Full Close");
        SetActionResult(ActionContext);
    end;

    /// <summary>Creates the closing journal for the recent closed years without posting it.</summary>
    [ServiceEnabled]
    procedure createClosingJournal(var ActionContext: WebServiceActionContext)
    var
        Runner: Codeunit "FYC Close Runner";
    begin
        Runner.Execute("FYC Run Mode"::"Create Closing Journal");
        SetActionResult(ActionContext);
    end;

    /// <summary>Posts the reviewed closing lines in the batch, opening the posting window if the setup says so.</summary>
    [ServiceEnabled]
    procedure postClosingJournal(var ActionContext: WebServiceActionContext)
    var
        Runner: Codeunit "FYC Close Runner";
    begin
        Runner.Execute("FYC Run Mode"::"Post Closing Journal");
        SetActionResult(ActionContext);
    end;

    /// <summary>Creates the daily recurring Job Queue entry if it does not exist yet.</summary>
    [ServiceEnabled]
    procedure createJobQueueEntry(var ActionContext: WebServiceActionContext)
    var
        JobQueueHandler: Codeunit "FYC Job Queue Handler";
    begin
        JobQueueHandler.CreateJobQueueEntry();
        SetActionResult(ActionContext);
    end;

    local procedure SetActionResult(var ActionContext: WebServiceActionContext)
    begin
        ActionContext.SetObjectType(ObjectType::Page);
        ActionContext.SetObjectId(Page::"FYC Close Setup API");
        ActionContext.AddEntityKey(Rec.FieldNo(SystemId), Rec.SystemId);
        ActionContext.SetResultCode(WebServiceActionResultCode::Updated);
    end;
}
