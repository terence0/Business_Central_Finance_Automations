page 68300 "FYC Close Setup"
{
    Caption = 'Fiscal Year Close Automation Setup';
    PageType = Card;
    SourceTable = "FYC Close Setup";
    UsageCategory = Administration;
    ApplicationArea = All;
    InsertAllowed = false;
    DeleteAllowed = false;

    layout
    {
        area(Content)
        {
            group(General)
            {
                Caption = 'General';
                field(Enabled; Rec.Enabled) { ApplicationArea = All; }
                field("Target Fiscal Year End"; Rec."Target Fiscal Year End") { ApplicationArea = All; Style = Strong; }
                field("Close Delay (Days)"; Rec."Close Delay (Days)") { ApplicationArea = All; }
                field("Earliest Fiscal Year Start"; Rec."Earliest Fiscal Year Start") { ApplicationArea = All; }
                field("Re-close Lookback (Years)"; Rec."Re-close Lookback (Years)") { ApplicationArea = All; }
            }
            group(FiscalYear)
            {
                Caption = 'Next Fiscal Year';
                field("Auto-Create Next Fiscal Year"; Rec."Auto-Create Next Fiscal Year") { ApplicationArea = All; }
                field("Period Length"; Rec."Period Length") { ApplicationArea = All; }
                field("No. of Periods"; Rec."No. of Periods") { ApplicationArea = All; }
            }
            group(CloseIncomeStatement)
            {
                Caption = 'Close Income Statement';
                field("Gen. Journal Template Name"; Rec."Gen. Journal Template Name") { ApplicationArea = All; }
                field("Gen. Journal Batch Name"; Rec."Gen. Journal Batch Name") { ApplicationArea = All; }
                field("Retained Earnings Acc."; Rec."Retained Earnings Acc.") { ApplicationArea = All; }
                field("Document No. Prefix"; Rec."Document No. Prefix") { ApplicationArea = All; }
                field("Posting Description"; Rec."Posting Description") { ApplicationArea = All; }
                field("Close by Business Unit"; Rec."Close by Business Unit") { ApplicationArea = All; }
                field("Close by Global Dimension 1"; Rec."Close by Global Dimension 1") { ApplicationArea = All; }
                field("Close by Global Dimension 2"; Rec."Close by Global Dimension 2") { ApplicationArea = All; }
                field("Post Automatically"; Rec."Post Automatically") { ApplicationArea = All; }
            }
            group(PostingWindow)
            {
                Caption = 'Posting Window';
                field("Open Posting Window"; Rec."Open Posting Window") { ApplicationArea = All; }
                field("Window User ID"; Rec."Window User ID") { ApplicationArea = All; }
                field("Window Saved From"; Rec."Window Saved From") { ApplicationArea = All; }
                field("Window Saved To"; Rec."Window Saved To") { ApplicationArea = All; }
                field("Window Opened At"; Rec."Window Opened At") { ApplicationArea = All; }
            }
        }
    }

    actions
    {
        area(Processing)
        {
            action(RunNow)
            {
                Caption = 'Run Now';
                ApplicationArea = All;
                Image = Start;
                ToolTip = 'Runs the full automation now: closes due fiscal years and runs Close Income Statement, posting if Post Automatically is on.';

                trigger OnAction()
                var
                    Runner: Codeunit "FYC Close Runner";
                    ConfirmQst: Label 'Close all due fiscal years and run Close Income Statement now?';
                begin
                    if Confirm(ConfirmQst, false) then
                        Runner.Execute("FYC Run Mode"::"Full Close");
                end;
            }
            action(CreateJournalOnly)
            {
                Caption = 'Create Closing Journal (No Posting)';
                ApplicationArea = All;
                Image = CloseYear;
                ToolTip = 'Creates the closing journal lines for the most recent closed fiscal years without posting them, so you can review them first.';

                trigger OnAction()
                var
                    Runner: Codeunit "FYC Close Runner";
                begin
                    Runner.Execute("FYC Run Mode"::"Create Closing Journal");
                end;
            }
            action(PostJournal)
            {
                Caption = 'Post Closing Journal';
                ApplicationArea = All;
                Image = PostBatch;
                ToolTip = 'Posts the reviewed closing lines in the journal batch. With Open Posting Window on, the closing date is allowed for you only while it posts.';

                trigger OnAction()
                var
                    Runner: Codeunit "FYC Close Runner";
                    ConfirmQst: Label 'Post the closing journal in batch %1 %2?', Comment = '%1 = template, %2 = batch';
                begin
                    if Confirm(ConfirmQst, false, Rec."Gen. Journal Template Name", Rec."Gen. Journal Batch Name") then
                        Runner.Execute("FYC Run Mode"::"Post Closing Journal");
                end;
            }
            action(Schedule)
            {
                Caption = 'Create Job Queue Entry';
                ApplicationArea = All;
                Image = Timesheet;
                ToolTip = 'Creates a daily recurring Job Queue entry that runs the automation.';

                trigger OnAction()
                var
                    JobQueueHandler: Codeunit "FYC Job Queue Handler";
                begin
                    JobQueueHandler.ScheduleJobQueueEntry();
                end;
            }
        }
        area(Navigation)
        {
            action(Log)
            {
                Caption = 'Log';
                ApplicationArea = All;
                Image = Log;
                RunObject = page "FYC Close Log";
                ToolTip = 'Shows what the automation has done.';
            }
            action(AccountingPeriods)
            {
                Caption = 'Accounting Periods';
                ApplicationArea = All;
                Image = AccountingPeriods;
                RunObject = page "Accounting Periods";
                ToolTip = 'Opens the accounting periods.';
            }
        }
        area(Promoted)
        {
            actionref(RunNow_Promoted; RunNow) { }
            actionref(CreateJournalOnly_Promoted; CreateJournalOnly) { }
            actionref(PostJournal_Promoted; PostJournal) { }
            actionref(Schedule_Promoted; Schedule) { }
            actionref(Log_Promoted; Log) { }
        }
    }

    trigger OnOpenPage()
    begin
        Rec.GetSetup();
    end;
}
