codeunit 68303 "FYC Close Logger"
{
    // Writes every close log entry. Single instance, so all entries written during one run
    // share its Run ID and can be read back together, whichever codeunit wrote them.
    SingleInstance = true;
    Permissions = tabledata "FYC Close Log" = ri;

    var
        RunId: Guid;
        RunStartedMsg: Label '%1 started.', Comment = '%1 = run mode';
        RunCompletedMsg: Label '%1 completed.', Comment = '%1 = run mode';

    procedure StartRun(Mode: Enum "FYC Run Mode")
    begin
        RunId := CreateGuid();
        Log("FYC Log Action"::"Run Started", 0D, 0D, '', 0, 0, StrSubstNo(RunStartedMsg, Mode));
    end;

    /// <summary>Closes the run with a Run Completed or Run Failed entry, then forgets the Run ID.</summary>
    procedure FinishRun(Mode: Enum "FYC Run Mode"; Succeeded: Boolean; ErrorText: Text)
    begin
        if Succeeded then
            Log("FYC Log Action"::"Run Completed", 0D, 0D, '', 0, 0, StrSubstNo(RunCompletedMsg, Mode))
        else
            Log("FYC Log Action"::"Run Failed", 0D, 0D, '', 0, 0, ErrorText);
        Clear(RunId);
    end;

    procedure Log(LogAction: Enum "FYC Log Action"; FYStart: Date; FYEnd: Date; DocNo: Code[20]; NoOfLines: Integer; RetainedEarningsAmount: Decimal; MessageText: Text)
    var
        CloseLog: Record "FYC Close Log";
    begin
        CloseLog.Init();
        CloseLog."Created At" := CurrentDateTime();
        CloseLog."Run ID" := RunId;
        CloseLog."Log Action" := LogAction;
        CloseLog.Status := StatusOf(LogAction);
        CloseLog."Fiscal Year Start" := FYStart;
        CloseLog."Fiscal Year End" := FYEnd;
        CloseLog."Document No." := DocNo;
        CloseLog."No. of Lines" := NoOfLines;
        CloseLog."Retained Earnings Amount" := RetainedEarningsAmount;
        CloseLog.Message := CopyStr(MessageText, 1, MaxStrLen(CloseLog.Message));
        CloseLog."User ID" := CopyStr(UserId(), 1, MaxStrLen(CloseLog."User ID"));
        CloseLog.Insert();
    end;

    local procedure StatusOf(LogAction: Enum "FYC Log Action"): Enum "FYC Log Status"
    begin
        case LogAction of
            "FYC Log Action"::"Fiscal Year Closed",
            "FYC Log Action"::"Next Fiscal Year Created",
            "FYC Log Action"::"Closing Journal Created",
            "FYC Log Action"::"Closing Journal Posted",
            "FYC Log Action"::"Check Passed",
            "FYC Log Action"::"Run Completed":
                exit("FYC Log Status"::Success);
            "FYC Log Action"::"Posting Failed",
            "FYC Log Action"::"Run Failed":
                exit("FYC Log Status"::Failed);
            else
                exit("FYC Log Status"::Info);
        end;
    end;
}
