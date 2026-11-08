codeunit 68301 "FYC Job Queue Handler"
{
    // Schedule this codeunit as a recurring Job Queue entry (daily is fine; it only acts when a year is due).
    TableNo = "Job Queue Entry";

    trigger OnRun()
    var
        Setup: Record "FYC Close Setup";
        Runner: Codeunit "FYC Close Runner";
    begin
        Setup.GetSetup();
        if not Setup.Enabled then
            exit;
        Runner.Execute("FYC Run Mode"::"Full Close");
    end;

    /// <summary>Page action: creates the Job Queue entry and tells the user what happened.</summary>
    procedure ScheduleJobQueueEntry()
    var
        AlreadyScheduledMsg: Label 'A Job Queue entry for the fiscal year close automation already exists.';
        ScheduledMsg: Label 'A daily Job Queue entry has been created and set to Ready. It runs at 02:00.';
    begin
        if CreateJobQueueEntry() then
            Message(ScheduledMsg)
        else
            Message(AlreadyScheduledMsg);
    end;

    /// <summary>Creates the daily 02:00 Job Queue entry without any dialogs, so it can be called from the API. Returns false if one already exists.</summary>
    procedure CreateJobQueueEntry(): Boolean
    var
        JobQueueEntry: Record "Job Queue Entry";
    begin
        if JobQueueEntryExists() then
            exit(false);

        JobQueueEntry.Init();
        JobQueueEntry."Object Type to Run" := JobQueueEntry."Object Type to Run"::Codeunit;
        JobQueueEntry."Object ID to Run" := Codeunit::"FYC Job Queue Handler";
        JobQueueEntry.Description := 'Fiscal year close and Close Income Statement';
        JobQueueEntry."Recurring Job" := true;
        JobQueueEntry."Run on Mondays" := true;
        JobQueueEntry."Run on Tuesdays" := true;
        JobQueueEntry."Run on Wednesdays" := true;
        JobQueueEntry."Run on Thursdays" := true;
        JobQueueEntry."Run on Fridays" := true;
        JobQueueEntry."Run on Saturdays" := true;
        JobQueueEntry."Run on Sundays" := true;
        JobQueueEntry."Starting Time" := 020000T;
        JobQueueEntry."Earliest Start Date/Time" := CreateDateTime(Today() + 1, 020000T);
        JobQueueEntry."Maximum No. of Attempts to Run" := 1;
        Codeunit.Run(Codeunit::"Job Queue - Enqueue", JobQueueEntry);
        exit(true);
    end;

    procedure JobQueueEntryExists(): Boolean
    var
        JobQueueEntry: Record "Job Queue Entry";
    begin
        JobQueueEntry.SetRange("Object Type to Run", JobQueueEntry."Object Type to Run"::Codeunit);
        JobQueueEntry.SetRange("Object ID to Run", Codeunit::"FYC Job Queue Handler");
        exit(not JobQueueEntry.IsEmpty());
    end;
}
