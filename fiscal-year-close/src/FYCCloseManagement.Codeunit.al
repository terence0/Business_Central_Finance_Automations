codeunit 68300 "FYC Close Management"
{
    // Automates two standard Business Central year-end tasks without any UI dialogs,
    // so they can run in a Job Queue (background) session:
    //   1. Close Fiscal Year (same effect as codeunit 6 "Fiscal Year-Close").
    //   2. Close Income Statement (same effect as report 94 "Close Income Statement"),
    //      followed by an optional post of the generated journal.
    // The income statement step is idempotent: it closes the net change of each income
    // statement account from the fiscal year start up to and including the closing date,
    // so a re-run only transfers late postings (the delta) to retained earnings.

    Permissions = tabledata "Accounting Period" = rim,
                  tabledata "Gen. Journal Line" = rimd,
                  tabledata "FYC Close Log" = ri;

    var
        Setup: Record "FYC Close Setup";
        PostingDate: Date;
        DocumentNo: Code[20];
        PostingDescription: Text[100];
        LineNo: Integer;
        LogAction: Enum "FYC Log Action";
        FirstOpenPeriodNotFYStartErr: Label 'The first open accounting period (%1) is not the start of a fiscal year. Correct the accounting periods before running the automation.', Comment = '%1 = starting date';
        OlderYearOpenErr: Label 'The oldest open fiscal year starts on %1, which is before the Earliest Fiscal Year Start (%2) in the setup. Close older years manually or adjust the setup.', Comment = '%1 = FY start, %2 = setup date';
        FiscalYearEndNotFoundErr: Label 'The fiscal year that starts on %1 has no following fiscal year, so its end date cannot be determined.', Comment = '%1 = FY start';
        BatchNotEmptyErr: Label 'Journal batch %1 %2 must be empty before the closing entries can be created. Post or delete the existing lines.', Comment = '%1 = template, %2 = batch';
        PostingDateNotAllowedErr: Label 'Posting date %1 is outside the allowed posting range for user %2. Widen Allow Posting From/To in General Ledger Setup or User Setup.', Comment = '%1 = posting date, %2 = user id';
        NothingToCloseMsg: Label 'All income statement accounts already net to zero for this fiscal year.';
        NextFYMissingMsg: Label 'The fiscal year starting %1 cannot be closed because the next fiscal year has not been created.', Comment = '%1 = FY start';
        NothingToPostErr: Label 'Journal batch %1 %2 has no lines to post.', Comment = '%1 = template, %2 = batch';
        NotClosingLineErr: Label 'Line %1 in journal batch %2 %3 is not a closing entry from this automation (it needs a closing date and source code %4). Only closing entries can be posted from here.', Comment = '%1 = line no., %2 = template, %3 = batch, %4 = source code';
        SetupCheckedMsg: Label 'Setup checked: journal batch %1 %2, retained earnings account %3.', Comment = '%1 = template, %2 = batch, %3 = account';
        NoOpenYearMsg: Label 'There is no open fiscal year to close.';
        NotDueMsg: Label 'Left the next fiscal year (%1 to %2) open: it is not due for closing until %3 (year end plus a close delay of %4 days). Nothing was done to it.', Comment = '%1 = FY start, %2 = FY end, %3 = due date, %4 = days';
        NoClosedYearMsg: Label 'No closed fiscal year on or after the Earliest Fiscal Year Start (%1) was found, so there is no income statement to close. Close the fiscal year first, or run the full close.', Comment = '%1 = date';
        TargetMsg: Label 'Target fiscal year: %1 to %2. Only this year is acted on; later years are never touched.', Comment = '%1 = FY start, %2 = FY end';
        TargetNotFoundErr: Label 'No fiscal year ends on %1 in this company (no fiscal year starts on %2). Nothing was closed. Check the year chosen against Accounting Periods.', Comment = '%1 = chosen year end, %2 = day after';
        TargetNotEndedErr: Label 'The fiscal year %1 to %2 has not ended yet, so it cannot be closed. Nothing was closed. Check the year chosen.', Comment = '%1 = FY start, %2 = FY end';
        TargetNotDueErr: Label 'The fiscal year %1 to %2 is not due for closing until %3 (year end plus a close delay of %4 days). Nothing was closed.', Comment = '%1 = FY start, %2 = FY end, %3 = due date, %4 = days';
        TargetEarlierOpenErr: Label 'An earlier fiscal year (%1 to %2) is still open, so %3 to %4 cannot be closed yet. Nothing was closed. Close the earlier year first by choosing it as the year to close.', Comment = '%1/%2 = earlier FY, %3/%4 = chosen FY';
        TargetBeforeEarliestErr: Label 'The fiscal year %1 to %2 starts before the Earliest Fiscal Year Start (%3) in the setup. Nothing was closed.', Comment = '%1/%2 = FY, %3 = setup date';
        TargetAlreadyClosedMsg: Label 'The fiscal year %1 to %2 is already closed, so it was not closed again. Only its closing journal is handled.', Comment = '%1 = FY start, %2 = FY end';
        TargetStillOpenErr: Label 'The fiscal year %1 to %2 is still open, so its closing journal cannot be created. Use Run full close to close the year and create the journal.', Comment = '%1 = FY start, %2 = FY end';
        WrongYearInBatchErr: Label 'Journal batch %1 %2 holds closing entries dated %3, which is not the closing date of the fiscal year chosen (%4). Nothing was posted. Check the year chosen, or delete the lines and create the journal again.', Comment = '%1 = template, %2 = batch, %3 = date in batch, %4 = expected closing date';

    /// <summary>Full run used by the Job Queue: create next FY if needed, close due years, close the income statement.</summary>
    procedure RunAutomatedClose()
    var
        PostingWindow: Codeunit "FYC Posting Window";
    begin
        PostingWindow.RestoreLeftover();
        GetSetup();
        Setup.CheckJournalSetup();
        InsertLog(LogAction::"Check Passed", 0D, 0D, '', 0, 0, StrSubstNo(SetupCheckedMsg,
          Setup."Gen. Journal Template Name", Setup."Gen. Journal Batch Name", Setup."Retained Earnings Acc."));

        if Setup."Target Fiscal Year End" <> 0D then begin
            RunTargetedClose(Setup."Target Fiscal Year End");
            exit;
        end;

        if Setup."Auto-Create Next Fiscal Year" then
            EnsureFutureFiscalYearExists();

        CloseDueFiscalYears();
        Commit();

        CloseIncomeStatementForRecentYears(Setup."Post Automatically");
    end;

    /// <summary>Runs Close Income Statement for the most recent closed fiscal years (per the lookback setting).</summary>
    procedure CloseIncomeStatementForRecentYears(PostJournal: Boolean)
    var
        AccountingPeriod: Record "Accounting Period";
        PostingWindow: Codeunit "FYC Posting Window";
        FYStarts: List of [Date];
        FYStart: Date;
        i: Integer;
    begin
        PostingWindow.RestoreLeftover();
        GetSetup();

        if Setup."Target Fiscal Year End" <> 0D then begin
            FYStart := GetTargetFiscalYearStart(Setup."Target Fiscal Year End");
            if not IsFiscalYearClosed(FYStart) then
                Error(TargetStillOpenErr, FormatDate(FYStart), FormatDate(Setup."Target Fiscal Year End"));
            CloseIncomeStatement(FYStart, Setup."Target Fiscal Year End", PostJournal);
            exit;
        end;

        AccountingPeriod.SetRange("New Fiscal Year", true);
        AccountingPeriod.SetRange(Closed, true);
        if Setup."Earliest Fiscal Year Start" <> 0D then
            AccountingPeriod.SetFilter("Starting Date", '>=%1', Setup."Earliest Fiscal Year Start");
        AccountingPeriod.Ascending(false);
        if AccountingPeriod.FindSet() then
            repeat
                FYStarts.Add(AccountingPeriod."Starting Date");
            until (AccountingPeriod.Next() = 0) or (FYStarts.Count() >= Setup."Re-close Lookback (Years)");

        if FYStarts.Count() = 0 then
            InsertLog(LogAction::Information, 0D, 0D, '', 0, 0, StrSubstNo(NoClosedYearMsg, FormatDate(Setup."Earliest Fiscal Year Start")));

        // Oldest first, so retained earnings builds up in chronological order.
        for i := FYStarts.Count() downto 1 do begin
            FYStart := FYStarts.Get(i);
            CloseIncomeStatement(FYStart, GetFiscalYearEnd(FYStart), PostJournal);
            Commit();
        end;
    end;

    /// <summary>Closes exactly the fiscal year ending TargetEnd (if still open) and creates its closing journal. Never touches any other year.</summary>
    local procedure RunTargetedClose(TargetEnd: Date)
    var
        AccountingPeriod: Record "Accounting Period";
        FYStart: Date;
    begin
        FYStart := GetTargetFiscalYearStart(TargetEnd);
        InsertLog(LogAction::"Check Passed", FYStart, TargetEnd, '', 0, 0, StrSubstNo(TargetMsg, FormatDate(FYStart), FormatDate(TargetEnd)));

        if IsFiscalYearClosed(FYStart) then
            InsertLog(LogAction::Information, FYStart, TargetEnd, '', 0, 0, StrSubstNo(TargetAlreadyClosedMsg, FormatDate(FYStart), FormatDate(TargetEnd)))
        else begin
            if Today() <= TargetEnd then
                Error(TargetNotEndedErr, FormatDate(FYStart), FormatDate(TargetEnd));
            if Today() < TargetEnd + Setup."Close Delay (Days)" then
                Error(TargetNotDueErr, FormatDate(FYStart), FormatDate(TargetEnd), FormatDate(TargetEnd + Setup."Close Delay (Days)"), Setup."Close Delay (Days)");
            if (Setup."Earliest Fiscal Year Start" <> 0D) and (FYStart < Setup."Earliest Fiscal Year Start") then
                Error(TargetBeforeEarliestErr, FormatDate(FYStart), FormatDate(TargetEnd), FormatDate(Setup."Earliest Fiscal Year Start"));

            // Closing a year leaves every earlier year closed, so the oldest open period must start this one.
            AccountingPeriod.SetRange(Closed, false);
            AccountingPeriod.FindFirst();
            if AccountingPeriod."Starting Date" < FYStart then
                Error(TargetEarlierOpenErr, FormatDate(GetFiscalYearStartOf(AccountingPeriod."Starting Date")),
                  FormatDate(GetFiscalYearEnd(GetFiscalYearStartOf(AccountingPeriod."Starting Date"))), FormatDate(FYStart), FormatDate(TargetEnd));

            CloseFiscalYear(FYStart, TargetEnd + 1);
            Commit();
        end;

        CloseIncomeStatement(FYStart, TargetEnd, Setup."Post Automatically");
    end;

    /// <summary>Start of the fiscal year that ends on TargetEnd. Errors if no fiscal year ends on that date.</summary>
    local procedure GetTargetFiscalYearStart(TargetEnd: Date): Date
    var
        AccountingPeriod: Record "Accounting Period";
    begin
        // A fiscal year ends on TargetEnd only if the next one starts the day after.
        AccountingPeriod.SetRange("New Fiscal Year", true);
        AccountingPeriod.SetRange("Starting Date", TargetEnd + 1);
        if AccountingPeriod.IsEmpty() then
            Error(TargetNotFoundErr, FormatDate(TargetEnd), FormatDate(TargetEnd + 1));
        exit(GetFiscalYearStartOf(TargetEnd));
    end;

    local procedure GetFiscalYearStartOf(DateInYear: Date): Date
    var
        AccountingPeriod: Record "Accounting Period";
    begin
        AccountingPeriod.SetRange("New Fiscal Year", true);
        AccountingPeriod.SetFilter("Starting Date", '<=%1', DateInYear);
        AccountingPeriod.FindLast();
        exit(AccountingPeriod."Starting Date");
    end;

    local procedure IsFiscalYearClosed(FYStart: Date): Boolean
    var
        AccountingPeriod: Record "Accounting Period";
    begin
        AccountingPeriod.Get(FYStart);
        exit(AccountingPeriod.Closed);
    end;

    /// <summary>Creates (and optionally posts) the closing journal for one closed fiscal year.</summary>
    procedure CloseIncomeStatement(FYStart: Date; FYEnd: Date; PostJournal: Boolean)
    var
        GenJnlLine: Record "Gen. Journal Line";
        TempClosingBuffer: Record "FYC Closing Buffer" temporary;
        TempRetainedBuffer: Record "FYC Closing Buffer" temporary;
        UserSetupMgt: Codeunit "User Setup Management";
        NoOfLines: Integer;
        RetainedEarningsTotal: Decimal;
    begin
        GetSetup();
        Setup.CheckJournalSetup();
        CheckFiscalYearClosed(FYStart);

        PostingDate := ClosingDate(FYEnd);
        // With the posting window on, the date is allowed just for the post; otherwise fail before creating lines.
        if PostJournal and not Setup."Open Posting Window" then
            if not UserSetupMgt.IsPostingDateValid(PostingDate) then
                Error(PostingDateNotAllowedErr, FormatDate(PostingDate), UserId());

        GenJnlLine.SetRange("Journal Template Name", Setup."Gen. Journal Template Name");
        GenJnlLine.SetRange("Journal Batch Name", Setup."Gen. Journal Batch Name");
        if not GenJnlLine.IsEmpty() then
            Error(BatchNotEmptyErr, Setup."Gen. Journal Template Name", Setup."Gen. Journal Batch Name");

        BuildClosingBuffer(FYStart, FYEnd, TempClosingBuffer);
        if TempClosingBuffer.IsEmpty() then begin
            InsertLog(LogAction::"Nothing to Close", FYStart, FYEnd, '', 0, 0, NothingToCloseMsg);
            exit;
        end;

        DocumentNo := GetDocumentNo(FYEnd);
        PostingDescription := CopyStr(StrSubstNo(Setup."Posting Description", FYEnd), 1, MaxStrLen(PostingDescription));
        LineNo := 0;

        // One line per income statement account (and grouping), reversing its net change.
        TempClosingBuffer.FindSet();
        repeat
            InsertJournalLine(TempClosingBuffer, TempClosingBuffer."G/L Account No.",
              -TempClosingBuffer.Amount, -TempClosingBuffer."Additional-Currency Amount");
            NoOfLines += 1;
            AddToRetainedBuffer(TempRetainedBuffer, TempClosingBuffer);
        until TempClosingBuffer.Next() = 0;

        // Balancing line to retained earnings: one total, or one per business unit when closing by business unit.
        TempRetainedBuffer.FindSet();
        repeat
            InsertJournalLine(TempRetainedBuffer, Setup."Retained Earnings Acc.",
              TempRetainedBuffer.Amount, TempRetainedBuffer."Additional-Currency Amount");
            NoOfLines += 1;
            RetainedEarningsTotal += TempRetainedBuffer.Amount;
        until TempRetainedBuffer.Next() = 0;

        InsertLog(LogAction::"Closing Journal Created", FYStart, FYEnd, DocumentNo, NoOfLines, RetainedEarningsTotal, '');
        Commit();

        if PostJournal then
            PostClosingJournal(FYStart, FYEnd, NoOfLines, RetainedEarningsTotal);
    end;

    local procedure GetDocumentNo(FYEnd: Date): Code[20]
    var
        GenJnlBatch: Record "Gen. Journal Batch";
        NoSeries: Codeunit "No. Series";
    begin
        // A batch with a No. Series makes posting insist on its next number, as the manual close uses.
        // Peek only: posting the batch is what takes the number from the series.
        GenJnlBatch.Get(Setup."Gen. Journal Template Name", Setup."Gen. Journal Batch Name");
        if GenJnlBatch."No. Series" <> '' then
            exit(NoSeries.PeekNextNo(GenJnlBatch."No. Series", FYEnd));
        exit(CopyStr(Setup."Document No. Prefix" + Format(Date2DMY(FYEnd, 3)), 1, 20));
    end;

    local procedure BuildClosingBuffer(FYStart: Date; FYEnd: Date; var TempClosingBuffer: Record "FYC Closing Buffer" temporary)
    var
        ISNetChange: Query "FYC IS Net Change";
        BusinessUnitCode: Code[20];
        Dim1Code: Code[20];
        Dim2Code: Code[20];
    begin
        // Includes the closing date, so earlier closing entries are netted off (delta behaviour).
        ISNetChange.SetRange(PostingDate, FYStart, ClosingDate(FYEnd));
        ISNetChange.Open();
        while ISNetChange.Read() do begin
            BusinessUnitCode := '';
            Dim1Code := '';
            Dim2Code := '';
            if Setup."Close by Business Unit" then
                BusinessUnitCode := ISNetChange.BusinessUnitCode;
            if Setup."Close by Global Dimension 1" then
                Dim1Code := ISNetChange.GlobalDim1Code;
            if Setup."Close by Global Dimension 2" then
                Dim2Code := ISNetChange.GlobalDim2Code;

            if not TempClosingBuffer.Get(ISNetChange.GLAccountNo, BusinessUnitCode, Dim1Code, Dim2Code) then begin
                TempClosingBuffer.Init();
                TempClosingBuffer."G/L Account No." := ISNetChange.GLAccountNo;
                TempClosingBuffer."Business Unit Code" := BusinessUnitCode;
                TempClosingBuffer."Global Dimension 1 Code" := Dim1Code;
                TempClosingBuffer."Global Dimension 2 Code" := Dim2Code;
                TempClosingBuffer.Insert();
            end;
            TempClosingBuffer.Amount += ISNetChange.Amount;
            TempClosingBuffer."Additional-Currency Amount" += ISNetChange.AddCurrencyAmount;
            TempClosingBuffer.Modify();
        end;
        ISNetChange.Close();

        TempClosingBuffer.SetRange(Amount, 0);
        TempClosingBuffer.SetRange("Additional-Currency Amount", 0);
        TempClosingBuffer.DeleteAll();
        TempClosingBuffer.Reset();
    end;

    local procedure AddToRetainedBuffer(var TempRetainedBuffer: Record "FYC Closing Buffer" temporary; TempClosingBuffer: Record "FYC Closing Buffer" temporary)
    begin
        // Retained earnings is one total line without dimensions, as the manual Close Income Statement
        // posts it, however finely the income statement lines are split. Only a business unit split
        // is kept, so each business unit still balances on its own.
        if not TempRetainedBuffer.Get('', TempClosingBuffer."Business Unit Code", '', '') then begin
            TempRetainedBuffer.Init();
            TempRetainedBuffer."Business Unit Code" := TempClosingBuffer."Business Unit Code";
            TempRetainedBuffer.Insert();
        end;
        // Retained earnings receives the net change (the opposite of the closing lines).
        TempRetainedBuffer.Amount += TempClosingBuffer.Amount;
        TempRetainedBuffer."Additional-Currency Amount" += TempClosingBuffer."Additional-Currency Amount";
        TempRetainedBuffer.Modify();
    end;

    local procedure InsertJournalLine(Grouping: Record "FYC Closing Buffer" temporary; AccountNo: Code[20]; LineAmount: Decimal; AddCurrAmount: Decimal)
    var
        GenJnlLine: Record "Gen. Journal Line";
        GenJnlBatch: Record "Gen. Journal Batch";
        GLSetup: Record "General Ledger Setup";
        SourceCodeSetup: Record "Source Code Setup";
    begin
        GLSetup.Get();
        SourceCodeSetup.Get();
        GenJnlBatch.Get(Setup."Gen. Journal Template Name", Setup."Gen. Journal Batch Name");
        LineNo += 10000;

        // Fields are assigned directly (as report 94 does) so no VAT, posting groups,
        // default dimensions or balancing accounts are pulled in from the G/L account or batch.
        GenJnlLine.Init();
        GenJnlLine."Journal Template Name" := Setup."Gen. Journal Template Name";
        GenJnlLine."Journal Batch Name" := Setup."Gen. Journal Batch Name";
        GenJnlLine."Line No." := LineNo;
        GenJnlLine."Posting Date" := PostingDate;
        GenJnlLine."Document Date" := NormalDate(PostingDate);
        GenJnlLine."Document No." := DocumentNo;
        GenJnlLine."Account Type" := GenJnlLine."Account Type"::"G/L Account";
        GenJnlLine."Account No." := AccountNo;
        GenJnlLine.Description := PostingDescription;
        GenJnlLine."Gen. Posting Type" := GenJnlLine."Gen. Posting Type"::" ";
        GenJnlLine."Business Unit Code" := Grouping."Business Unit Code";
        GenJnlLine."Source Code" := SourceCodeSetup."Close Income Statement";
        GenJnlLine."Reason Code" := GenJnlBatch."Reason Code";
        GenJnlLine."Posting No. Series" := GenJnlBatch."Posting No. Series";
        GenJnlLine."System-Created Entry" := true;

        GenJnlLine.Amount := LineAmount;
        GenJnlLine."Amount (LCY)" := LineAmount;
        GenJnlLine."Balance (LCY)" := LineAmount;
        if LineAmount > 0 then
            GenJnlLine."Debit Amount" := LineAmount
        else
            GenJnlLine."Credit Amount" := -LineAmount;
        if LineAmount = 0 then
            GenJnlLine."Allow Zero-Amount Posting" := true; // ACY-only rounding difference

        if GLSetup."Additional Reporting Currency" <> '' then begin
            GenJnlLine."Source Currency Code" := GLSetup."Additional Reporting Currency";
            GenJnlLine."Source Currency Amount" := AddCurrAmount;
        end;

        // Set directly rather than validated: validation rejects blocked values, and old cost centres
        // that are blocked today can still carry a balance for the year. The posting window unblocks
        // them for the post.
        GenJnlLine."Shortcut Dimension 1 Code" := Grouping."Global Dimension 1 Code";
        GenJnlLine."Shortcut Dimension 2 Code" := Grouping."Global Dimension 2 Code";
        GenJnlLine."Dimension Set ID" := GetGlobalDimSetID(GLSetup, Grouping."Global Dimension 1 Code", Grouping."Global Dimension 2 Code");

        GenJnlLine.Insert();
    end;

    local procedure GetGlobalDimSetID(GLSetup: Record "General Ledger Setup"; Dim1Code: Code[20]; Dim2Code: Code[20]): Integer
    var
        TempDimSetEntry: Record "Dimension Set Entry" temporary;
        DimMgt: Codeunit DimensionManagement;
    begin
        if (Dim1Code = '') and (Dim2Code = '') then
            exit(0);
        AddDimSetEntry(TempDimSetEntry, GLSetup."Global Dimension 1 Code", Dim1Code);
        AddDimSetEntry(TempDimSetEntry, GLSetup."Global Dimension 2 Code", Dim2Code);
        exit(DimMgt.GetDimensionSetID(TempDimSetEntry));
    end;

    local procedure AddDimSetEntry(var TempDimSetEntry: Record "Dimension Set Entry" temporary; DimensionCode: Code[20]; ValueCode: Code[20])
    var
        DimValue: Record "Dimension Value";
    begin
        if (DimensionCode = '') or (ValueCode = '') then
            exit;
        DimValue.Get(DimensionCode, ValueCode);
        TempDimSetEntry.Init();
        TempDimSetEntry."Dimension Code" := DimensionCode;
        TempDimSetEntry."Dimension Value Code" := ValueCode;
        TempDimSetEntry."Dimension Value ID" := DimValue."Dimension Value ID";
        TempDimSetEntry.Insert();
    end;

    /// <summary>Posts closing lines already in the batch, for example after reviewing a journal created without posting.</summary>
    procedure PostReviewedClosingJournal()
    var
        GenJnlLine: Record "Gen. Journal Line";
        AccountingPeriod: Record "Accounting Period";
        SourceCodeSetup: Record "Source Code Setup";
        PostingWindow: Codeunit "FYC Posting Window";
        FYEnd: Date;
        NoOfLines: Integer;
        RetainedEarningsTotal: Decimal;
    begin
        PostingWindow.RestoreLeftover();
        GetSetup();
        Setup.CheckJournalSetup();
        SourceCodeSetup.Get();

        GenJnlLine.SetRange("Journal Template Name", Setup."Gen. Journal Template Name");
        GenJnlLine.SetRange("Journal Batch Name", Setup."Gen. Journal Batch Name");
        if not GenJnlLine.FindSet() then
            Error(NothingToPostErr, Setup."Gen. Journal Template Name", Setup."Gen. Journal Batch Name");

        // The posting window allows the closing date, so refuse anything that is not a closing entry.
        PostingDate := GenJnlLine."Posting Date";
        DocumentNo := GenJnlLine."Document No.";
        repeat
            if (GenJnlLine."Posting Date" <> PostingDate) or (PostingDate = NormalDate(PostingDate)) or
               (GenJnlLine."Source Code" <> SourceCodeSetup."Close Income Statement")
            then
                Error(NotClosingLineErr, GenJnlLine."Line No.", Setup."Gen. Journal Template Name",
                  Setup."Gen. Journal Batch Name", SourceCodeSetup."Close Income Statement");
            NoOfLines += 1;
            if GenJnlLine."Account No." = Setup."Retained Earnings Acc." then
                RetainedEarningsTotal += GenJnlLine.Amount;
        until GenJnlLine.Next() = 0;

        if Setup."Target Fiscal Year End" <> 0D then
            if PostingDate <> ClosingDate(Setup."Target Fiscal Year End") then
                Error(WrongYearInBatchErr, Setup."Gen. Journal Template Name", Setup."Gen. Journal Batch Name",
                  FormatDate(PostingDate), FormatDate(ClosingDate(Setup."Target Fiscal Year End")));

        FYEnd := NormalDate(PostingDate);
        AccountingPeriod.SetRange("New Fiscal Year", true);
        AccountingPeriod.SetFilter("Starting Date", '<=%1', FYEnd);
        AccountingPeriod.FindLast();

        PostClosingJournal(AccountingPeriod."Starting Date", FYEnd, NoOfLines, RetainedEarningsTotal);
    end;

    local procedure PostClosingJournal(FYStart: Date; FYEnd: Date; NoOfLines: Integer; RetainedEarningsTotal: Decimal)
    var
        GenJnlLine: Record "Gen. Journal Line";
        PostingWindow: Codeunit "FYC Posting Window";
        Posted: Boolean;
        ErrorText: Text;
    begin
        GenJnlLine.SetRange("Journal Template Name", Setup."Gen. Journal Template Name");
        GenJnlLine.SetRange("Journal Batch Name", Setup."Gen. Journal Batch Name");
        GenJnlLine.FindFirst();

        // Open commits, so the saved dates survive even if the session dies mid-post.
        if Setup."Open Posting Window" then
            PostingWindow.Open(PostingDate, Setup."Gen. Journal Template Name", Setup."Gen. Journal Batch Name");

        // "Gen. Jnl.-Post Batch" posts without confirmation dialogs, so it is safe in the Job Queue.
        Posted := Codeunit.Run(Codeunit::"Gen. Jnl.-Post Batch", GenJnlLine);
        if not Posted then
            ErrorText := GetLastErrorText();

        if Setup."Open Posting Window" then
            PostingWindow.Restore();

        if Posted then begin
            InsertLog(LogAction::"Closing Journal Posted", FYStart, FYEnd, DocumentNo, NoOfLines, RetainedEarningsTotal, '');
            exit;
        end;

        InsertLog(LogAction::"Posting Failed", FYStart, FYEnd, DocumentNo, NoOfLines, RetainedEarningsTotal, ErrorText);
        Commit();
        Error(ErrorText);
    end;

    local procedure CloseDueFiscalYears()
    var
        FYStart: Date;
        NextFYStart: Date;
    begin
        while GetNextYearDueForClosing(FYStart, NextFYStart) do begin
            CloseFiscalYear(FYStart, NextFYStart);
            Commit();
        end;
    end;

    local procedure GetNextYearDueForClosing(var FYStart: Date; var NextFYStart: Date): Boolean
    var
        AccountingPeriod: Record "Accounting Period";
    begin
        AccountingPeriod.SetRange(Closed, false);
        if not AccountingPeriod.FindFirst() then begin
            InsertLog(LogAction::Information, 0D, 0D, '', 0, 0, NoOpenYearMsg);
            exit(false);
        end;
        if not AccountingPeriod."New Fiscal Year" then
            Error(FirstOpenPeriodNotFYStartErr, FormatDate(AccountingPeriod."Starting Date"));
        FYStart := AccountingPeriod."Starting Date";

        AccountingPeriod.Reset();
        AccountingPeriod.SetRange("New Fiscal Year", true);
        AccountingPeriod.SetFilter("Starting Date", '>%1', FYStart);
        if not AccountingPeriod.FindFirst() then begin
            if Today() > FYStart then
                InsertLog(LogAction::Skipped, FYStart, 0D, '', 0, 0, StrSubstNo(NextFYMissingMsg, FormatDate(FYStart)));
            exit(false);
        end;
        NextFYStart := AccountingPeriod."Starting Date";

        // Not due yet: fiscal year end + delay is still in the future.
        if Today() < (NextFYStart - 1) + Setup."Close Delay (Days)" then begin
            InsertLog(LogAction::Information, FYStart, NextFYStart - 1, '', 0, 0, StrSubstNo(NotDueMsg,
              FormatDate(FYStart), FormatDate(NextFYStart - 1), FormatDate((NextFYStart - 1) + Setup."Close Delay (Days)"), Setup."Close Delay (Days)"));
            exit(false);
        end;

        if (Setup."Earliest Fiscal Year Start" <> 0D) and (FYStart < Setup."Earliest Fiscal Year Start") then
            Error(OlderYearOpenErr, FormatDate(FYStart), FormatDate(Setup."Earliest Fiscal Year Start"));

        exit(true);
    end;

    local procedure CloseFiscalYear(FYStart: Date; NextFYStart: Date)
    var
        AccountingPeriod: Record "Accounting Period";
    begin
        // Same result as codeunit 6 "Fiscal Year-Close", without its Confirm dialog.
        AccountingPeriod.SetRange("Starting Date", FYStart, NextFYStart - 1);
        AccountingPeriod.ModifyAll(Closed, true);
        AccountingPeriod.ModifyAll("Date Locked", true);

        // Lock the start of the next year too, because it defines this year's end date.
        AccountingPeriod.Reset();
        if AccountingPeriod.Get(NextFYStart) then begin
            AccountingPeriod."Date Locked" := true;
            AccountingPeriod.Modify();
        end;

        InsertLog(LogAction::"Fiscal Year Closed", FYStart, NextFYStart - 1, '', 0, 0, '');
    end;

    local procedure EnsureFutureFiscalYearExists()
    var
        AccountingPeriod: Record "Accounting Period";
        i: Integer;
    begin
        if AccountingPeriod.IsEmpty() then
            exit;
        Setup.TestField("No. of Periods");

        // Create years until one starts after today (capped as a safety net).
        for i := 1 to 10 do begin
            AccountingPeriod.Reset();
            AccountingPeriod.SetRange("New Fiscal Year", true);
            AccountingPeriod.SetFilter("Starting Date", '>%1', Today());
            if not AccountingPeriod.IsEmpty() then
                exit;
            CreateFiscalYearAfterLastPeriod();
        end;
    end;

    local procedure CreateFiscalYearAfterLastPeriod()
    var
        LastPeriod: Record "Accounting Period";
        NewPeriod: Record "Accounting Period";
        InventorySetup: Record "Inventory Setup";
        StartDate: Date;
        FirstStartDate: Date;
        i: Integer;
    begin
        LastPeriod.FindLast();
        StartDate := CalcDate(Setup."Period Length", LastPeriod."Starting Date");
        FirstStartDate := StartDate;
        if not InventorySetup.Get() then
            InventorySetup.Init();

        // Same structure as report 93 "Create Fiscal Year".
        for i := 1 to Setup."No. of Periods" do begin
            NewPeriod.Init();
            NewPeriod.Validate("Starting Date", StartDate);
            if i = 1 then begin
                NewPeriod."New Fiscal Year" := true;
                NewPeriod."Average Cost Calc. Type" := InventorySetup."Average Cost Calc. Type";
                NewPeriod."Average Cost Period" := InventorySetup."Average Cost Period";
            end;
            NewPeriod.Insert();
            StartDate := CalcDate(Setup."Period Length", StartDate);
        end;

        InsertLog(LogAction::"Next Fiscal Year Created", FirstStartDate, StartDate - 1, '', Setup."No. of Periods", 0, '');
    end;

    local procedure CheckFiscalYearClosed(FYStart: Date)
    var
        AccountingPeriod: Record "Accounting Period";
    begin
        AccountingPeriod.Get(FYStart);
        AccountingPeriod.TestField("New Fiscal Year", true);
        AccountingPeriod.TestField(Closed, true);
    end;

    procedure GetFiscalYearEnd(FYStart: Date): Date
    var
        AccountingPeriod: Record "Accounting Period";
    begin
        AccountingPeriod.SetRange("New Fiscal Year", true);
        AccountingPeriod.SetFilter("Starting Date", '>%1', FYStart);
        if not AccountingPeriod.FindFirst() then
            Error(FiscalYearEndNotFoundErr, FormatDate(FYStart));
        exit(AccountingPeriod."Starting Date" - 1);
    end;

    local procedure FormatDate(Value: Date): Text
    begin
        // Log and error text is read by people in several regions; the run's user may format dates US-style.
        if Value = 0D then
            exit('(blank)');
        if Value <> NormalDate(Value) then
            exit('C' + Format(NormalDate(Value), 0, '<Day,2> <Month Text,3> <Year4>'));
        exit(Format(Value, 0, '<Day,2> <Month Text,3> <Year4>'));
    end;

    local procedure GetSetup()
    begin
        Setup.GetSetup();
    end;

    local procedure InsertLog(NewLogAction: Enum "FYC Log Action"; FYStart: Date; FYEnd: Date; DocNo: Code[20]; NoOfLines: Integer; RetainedEarningsAmount: Decimal; MessageText: Text)
    var
        Logger: Codeunit "FYC Close Logger";
    begin
        Logger.Log(NewLogAction, FYStart, FYEnd, DocNo, NoOfLines, RetainedEarningsAmount, MessageText);
    end;
}
