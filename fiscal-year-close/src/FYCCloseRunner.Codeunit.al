codeunit 68304 "FYC Close Runner"
{
    // Single entry point for every run (page actions, API actions, Job Queue). The work runs
    // inside Codeunit.Run, so an error is caught, written to the close log and committed before
    // it is raised again. Without this, an error rolls back its own log entry and the log shows
    // nothing at all for a failed run.

    var
        Mode: Enum "FYC Run Mode";

    trigger OnRun()
    var
        CloseMgt: Codeunit "FYC Close Management";
    begin
        case Mode of
            Mode::"Full Close":
                CloseMgt.RunAutomatedClose();
            Mode::"Create Closing Journal":
                CloseMgt.CloseIncomeStatementForRecentYears(false);
            Mode::"Post Closing Journal":
                CloseMgt.PostReviewedClosingJournal();
        end;
    end;

    /// <summary>Runs the given action with a Run Started entry, a log entry per step, and a Run Completed or Run Failed entry. Errors are raised again after logging.</summary>
    procedure Execute(RunMode: Enum "FYC Run Mode")
    var
        Runner: Codeunit "FYC Close Runner";
        Logger: Codeunit "FYC Close Logger";
        PostingWindow: Codeunit "FYC Posting Window";
        ErrorText: Text;
    begin
        // Codeunit.Run can only catch errors when no write transaction is open.
        Commit();
        Logger.StartRun(RunMode);
        Commit();

        Runner.SetMode(RunMode);
        ClearLastError();
        if Runner.Run() then begin
            Logger.FinishRun(RunMode, true, '');
            Commit();
            exit;
        end;

        ErrorText := GetLastErrorText();
        // Never leave the closing date allowed after a failure.
        PostingWindow.Restore();
        Logger.FinishRun(RunMode, false, ErrorText);
        Commit();
        Error(ErrorText);
    end;

    procedure SetMode(RunMode: Enum "FYC Run Mode")
    begin
        Mode := RunMode;
    end;
}
