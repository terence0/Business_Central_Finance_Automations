codeunit 68302 "FYC Posting Window"
{
    // Lets the closing journal post without leaving the ledger open or old dimension values
    // unblocked. Just before posting:
    //   - the running user's Allow Posting From/To in User Setup is narrowed to the closing date alone;
    //   - blocked dimension values used by the closing lines (old cost centres with a balance in
    //     the year) are unblocked;
    //   - default dimension posting rules (Value Posting) on the closing accounts are lifted, since
    //     the closing lines carry the dimensions of the entries they reverse.
    // Straight after, all of it is put back. What was changed is saved and committed before posting,
    // so a run that is cut off is restored by the next one.

    Permissions = tabledata "User Setup" = rim,
                  tabledata "Dimension Value" = rm,
                  tabledata "Default Dimension" = rm,
                  tabledata "FYC Relaxed Default Dim." = rid,
                  tabledata "Dimension Set Entry" = r,
                  tabledata "Gen. Journal Line" = r,
                  tabledata "FYC Close Setup" = rm,
                  tabledata "FYC Unblocked Dim. Value" = rid,
                  tabledata "FYC Close Log" = ri;

    var
        WindowOpenedMsg: Label 'Posting dates for user %1 temporarily set to the closing date %2 only. Before: %3.', Comment = '%1 = user, %2 = closing date, %3 = saved range';
        WindowRestoredMsg: Label 'Posting dates for user %1 restored to %2.', Comment = '%1 = user, %2 = restored range';
        WindowRestoredLateMsg: Label 'A posting window opened at %1 was left open by an interrupted run. Posting dates for user %2 restored to %3.', Comment = '%1 = datetime, %2 = user, %3 = restored range';
        RangeTxt: Label 'Allow Posting From %1 to %2 in User Setup', Comment = '%1/%2 = dates';
        FollowsGLSetupTxt: Label 'blank in User Setup, so the user follows General Ledger Setup (Allow Posting From %1 to %2)', Comment = '%1/%2 = dates';
        NoLimitTxt: Label 'no limit';
        DimsUnblockedMsg: Label 'Temporarily unblocked %1 dimension values used by the closing lines: %2', Comment = '%1 = count, %2 = list';
        DimsBlockedMsg: Label 'Blocked %1 dimension values again: %2', Comment = '%1 = count, %2 = list';
        DimsBlockedLateMsg: Label 'An interrupted run left %1 dimension values unblocked. Blocked them again: %2', Comment = '%1 = count, %2 = list';
        RulesLiftedMsg: Label 'Temporarily lifted %1 default dimension posting rules on the closing accounts: %2', Comment = '%1 = count, %2 = list';
        RulesRestoredMsg: Label 'Put back %1 default dimension posting rules: %2', Comment = '%1 = count, %2 = list';
        RulesRestoredLateMsg: Label 'An interrupted run left %1 default dimension posting rules lifted. Put them back: %2', Comment = '%1 = count, %2 = list';
        AllAccountsTxt: Label 'all accounts';

    /// <summary>Allows PostingDate (and only that date) for the current user, unblocks the blocked dimension values used in the batch, and lifts the default dimension posting rules on its accounts.</summary>
    procedure Open(PostingDate: Date; TemplateName: Code[10]; BatchName: Code[10])
    begin
        RestoreLeftover();
        OpenPostingDates(PostingDate);
        UnblockDimensionValues(TemplateName, BatchName);
        LiftDefaultDimensionRules(TemplateName, BatchName);
        Commit();
    end;

    /// <summary>Puts back what Open changed. Does nothing if no window is open.</summary>
    procedure Restore()
    begin
        RestoreWindow(false);
    end;

    /// <summary>Restores a window an interrupted run left open. Called at the start of every run.</summary>
    procedure RestoreLeftover()
    begin
        RestoreWindow(true);
    end;

    procedure IsOpen(): Boolean
    var
        Setup: Record "FYC Close Setup";
        Unblocked: Record "FYC Unblocked Dim. Value";
    begin
        if not Unblocked.IsEmpty() then
            exit(true);
        if not Setup.Get() then
            exit(false);
        exit(Setup."Window User ID" <> '');
    end;

    local procedure OpenPostingDates(PostingDate: Date)
    var
        Setup: Record "FYC Close Setup";
        UserSetup: Record "User Setup";
        UserSetupMgt: Codeunit "User Setup Management";
        CurrentUser: Code[50];
    begin
        if UserSetupMgt.IsPostingDateValid(PostingDate) then
            exit;

        CurrentUser := CopyStr(UserId(), 1, MaxStrLen(CurrentUser));
        if not UserSetup.Get(CurrentUser) then begin
            // A row with blank dates falls back to General Ledger Setup, so restoring blanks is the same as no row.
            UserSetup.Init();
            UserSetup."User ID" := CurrentUser;
            UserSetup.Insert();
        end;

        Setup.GetSetup();
        Setup."Window User ID" := CurrentUser;
        Setup."Window Saved From" := UserSetup."Allow Posting From";
        Setup."Window Saved To" := UserSetup."Allow Posting To";
        Setup."Window Opened At" := CurrentDateTime();
        Setup.Modify();

        UserSetup."Allow Posting From" := PostingDate;
        UserSetup."Allow Posting To" := PostingDate;
        UserSetup.Modify();

        InsertLog(StrSubstNo(WindowOpenedMsg, CurrentUser, FormatDate(PostingDate),
          DescribeRange(Setup."Window Saved From", Setup."Window Saved To")));
    end;

    local procedure DescribeRange(FromDate: Date; ToDate: Date): Text
    var
        GLSetup: Record "General Ledger Setup";
    begin
        if (FromDate <> 0D) or (ToDate <> 0D) then
            exit(StrSubstNo(RangeTxt, FormatDate(FromDate), FormatDate(ToDate)));
        GLSetup.Get();
        exit(StrSubstNo(FollowsGLSetupTxt, FormatDate(GLSetup."Allow Posting From"), FormatDate(GLSetup."Allow Posting To")));
    end;

    local procedure FormatDate(Value: Date): Text
    begin
        // Unambiguous whatever the language and region of the user the run executes as.
        if Value = 0D then
            exit(NoLimitTxt);
        if Value <> NormalDate(Value) then
            exit('C' + Format(NormalDate(Value), 0, '<Day,2> <Month Text,3> <Year4>'));
        exit(Format(Value, 0, '<Day,2> <Month Text,3> <Year4>'));
    end;

    local procedure UnblockDimensionValues(TemplateName: Code[10]; BatchName: Code[10])
    var
        GenJnlLine: Record "Gen. Journal Line";
        DimSetEntry: Record "Dimension Set Entry";
        DimValue: Record "Dimension Value";
        Unblocked: Record "FYC Unblocked Dim. Value";
        DoneSets: List of [Integer];
        List: TextBuilder;
        Count: Integer;
    begin
        GenJnlLine.SetRange("Journal Template Name", TemplateName);
        GenJnlLine.SetRange("Journal Batch Name", BatchName);
        GenJnlLine.SetFilter("Dimension Set ID", '<>0');
        if not GenJnlLine.FindSet() then
            exit;
        repeat
            if not DoneSets.Contains(GenJnlLine."Dimension Set ID") then begin
                DoneSets.Add(GenJnlLine."Dimension Set ID");
                DimSetEntry.SetRange("Dimension Set ID", GenJnlLine."Dimension Set ID");
                if DimSetEntry.FindSet() then
                    repeat
                        if not Unblocked.Get(DimSetEntry."Dimension Code", DimSetEntry."Dimension Value Code") then
                            if DimValue.Get(DimSetEntry."Dimension Code", DimSetEntry."Dimension Value Code") then
                                if DimValue.Blocked then begin
                                    Unblocked."Dimension Code" := DimValue."Dimension Code";
                                    Unblocked."Dimension Value Code" := DimValue.Code;
                                    Unblocked.Insert();
                                    // Modify(false): the block is lifted for seconds, so skip the table's own triggers.
                                    DimValue.Blocked := false;
                                    DimValue.Modify(false);
                                    AddToList(List, DimValue."Dimension Code", DimValue.Code);
                                    Count += 1;
                                end;
                    until DimSetEntry.Next() = 0;
            end;
        until GenJnlLine.Next() = 0;

        if Count > 0 then
            InsertLog(StrSubstNo(DimsUnblockedMsg, Count, List.ToText()));
    end;

    local procedure RestoreWindow(Leftover: Boolean)
    var
        Changed: Boolean;
    begin
        if RestorePostingDates(Leftover) then
            Changed := true;
        if ReblockDimensionValues(Leftover) then
            Changed := true;
        if RestoreDefaultDimensionRules(Leftover) then
            Changed := true;
        if Changed then
            Commit();
    end;

    local procedure LiftDefaultDimensionRules(TemplateName: Code[10]; BatchName: Code[10])
    var
        GenJnlLine: Record "Gen. Journal Line";
        Lifted: Record "FYC Relaxed Default Dim.";
        DoneAccounts: List of [Code[20]];
        List: TextBuilder;
        Count: Integer;
    begin
        // Rules such as Code Mandatory or Same Code may have been set up after the entries being
        // reversed were posted. Lift them on the closing accounts, and on the all-accounts default,
        // for the post only.
        GenJnlLine.SetRange("Journal Template Name", TemplateName);
        GenJnlLine.SetRange("Journal Batch Name", BatchName);
        GenJnlLine.SetRange("Account Type", GenJnlLine."Account Type"::"G/L Account");
        if not GenJnlLine.FindSet() then
            exit;
        DoneAccounts.Add('');
        LiftRulesFor('', Lifted, List, Count);
        repeat
            if not DoneAccounts.Contains(GenJnlLine."Account No.") then begin
                DoneAccounts.Add(GenJnlLine."Account No.");
                LiftRulesFor(GenJnlLine."Account No.", Lifted, List, Count);
            end;
        until GenJnlLine.Next() = 0;

        if Count > 0 then
            InsertLog(StrSubstNo(RulesLiftedMsg, Count, List.ToText()));
    end;

    local procedure LiftRulesFor(AccountNo: Code[20]; var Lifted: Record "FYC Relaxed Default Dim."; var List: TextBuilder; var Count: Integer)
    var
        DefaultDim: Record "Default Dimension";
    begin
        DefaultDim.SetRange("Table ID", Database::"G/L Account");
        DefaultDim.SetRange("No.", AccountNo);
        DefaultDim.SetFilter("Value Posting", '<>%1', DefaultDim."Value Posting"::" ");
        if not DefaultDim.FindSet() then
            exit;
        repeat
            if not Lifted.Get(DefaultDim."Table ID", DefaultDim."No.", DefaultDim."Dimension Code") then begin
                Lifted."Table ID" := DefaultDim."Table ID";
                Lifted."No." := DefaultDim."No.";
                Lifted."Dimension Code" := DefaultDim."Dimension Code";
                Lifted."Value Posting" := DefaultDim."Value Posting";
                Lifted.Insert();
                DefaultDim."Value Posting" := DefaultDim."Value Posting"::" ";
                DefaultDim.Modify(false);
                AddRuleToList(List, Lifted);
                Count += 1;
            end;
        until DefaultDim.Next() = 0;
    end;

    local procedure RestoreDefaultDimensionRules(Leftover: Boolean): Boolean
    var
        DefaultDim: Record "Default Dimension";
        Lifted: Record "FYC Relaxed Default Dim.";
        List: TextBuilder;
        Count: Integer;
    begin
        if not Lifted.FindSet() then
            exit(false);
        repeat
            if DefaultDim.Get(Lifted."Table ID", Lifted."No.", Lifted."Dimension Code") then begin
                DefaultDim."Value Posting" := Lifted."Value Posting";
                DefaultDim.Modify(false);
            end;
            AddRuleToList(List, Lifted);
            Count += 1;
        until Lifted.Next() = 0;
        Lifted.DeleteAll();

        if Leftover then
            InsertLog(StrSubstNo(RulesRestoredLateMsg, Count, List.ToText()))
        else
            InsertLog(StrSubstNo(RulesRestoredMsg, Count, List.ToText()));
        exit(true);
    end;

    local procedure AddRuleToList(var List: TextBuilder; Lifted: Record "FYC Relaxed Default Dim.")
    var
        AccountText: Text;
    begin
        AccountText := Lifted."No.";
        if AccountText = '' then
            AccountText := AllAccountsTxt;
        if List.Length() > 0 then
            List.Append(', ');
        List.Append(StrSubstNo('%1 %2 (%3)', AccountText, Lifted."Dimension Code", Lifted."Value Posting"));
    end;

    local procedure RestorePostingDates(Leftover: Boolean): Boolean
    var
        Setup: Record "FYC Close Setup";
        UserSetup: Record "User Setup";
    begin
        if not Setup.Get() then
            exit(false);
        if Setup."Window User ID" = '' then
            exit(false);

        if UserSetup.Get(Setup."Window User ID") then begin
            UserSetup."Allow Posting From" := Setup."Window Saved From";
            UserSetup."Allow Posting To" := Setup."Window Saved To";
            UserSetup.Modify();
        end;

        if Leftover then
            InsertLog(StrSubstNo(WindowRestoredLateMsg, Setup."Window Opened At", Setup."Window User ID",
              DescribeRange(Setup."Window Saved From", Setup."Window Saved To")))
        else
            InsertLog(StrSubstNo(WindowRestoredMsg, Setup."Window User ID",
              DescribeRange(Setup."Window Saved From", Setup."Window Saved To")));

        Setup."Window User ID" := '';
        Setup."Window Saved From" := 0D;
        Setup."Window Saved To" := 0D;
        Setup."Window Opened At" := 0DT;
        Setup.Modify();
        exit(true);
    end;

    local procedure ReblockDimensionValues(Leftover: Boolean): Boolean
    var
        DimValue: Record "Dimension Value";
        Unblocked: Record "FYC Unblocked Dim. Value";
        List: TextBuilder;
        Count: Integer;
    begin
        if not Unblocked.FindSet() then
            exit(false);
        repeat
            if DimValue.Get(Unblocked."Dimension Code", Unblocked."Dimension Value Code") then begin
                DimValue.Blocked := true;
                DimValue.Modify(false);
            end;
            AddToList(List, Unblocked."Dimension Code", Unblocked."Dimension Value Code");
            Count += 1;
        until Unblocked.Next() = 0;
        Unblocked.DeleteAll();

        if Leftover then
            InsertLog(StrSubstNo(DimsBlockedLateMsg, Count, List.ToText()))
        else
            InsertLog(StrSubstNo(DimsBlockedMsg, Count, List.ToText()));
        exit(true);
    end;

    local procedure AddToList(var List: TextBuilder; DimensionCode: Code[20]; ValueCode: Code[20])
    begin
        if List.Length() > 0 then
            List.Append(', ');
        List.Append(DimensionCode + ' ' + ValueCode);
    end;

    local procedure InsertLog(MessageText: Text)
    var
        Logger: Codeunit "FYC Close Logger";
    begin
        Logger.Log("FYC Log Action"::"Posting Window", 0D, 0D, '', 0, 0, MessageText);
    end;
}
