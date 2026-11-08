table 68300 "FYC Close Setup"
{
    Caption = 'Fiscal Year Close Automation Setup';
    DataClassification = CustomerContent;

    fields
    {
        field(1; "Primary Key"; Code[10])
        {
            Caption = 'Primary Key';
        }
        field(10; Enabled; Boolean)
        {
            Caption = 'Enabled';
            ToolTip = 'Specifies whether the scheduled Job Queue entry is allowed to run the automation.';
        }
        field(20; "Close Delay (Days)"; Integer)
        {
            Caption = 'Close Delay (Days)';
            MinValue = 0;
            InitValue = 30;
            ToolTip = 'Specifies how many days after the fiscal year end date the year is closed automatically. This leaves time for audit adjustments.';
        }
        field(21; "Earliest Fiscal Year Start"; Date)
        {
            Caption = 'Earliest Fiscal Year Start';
            ToolTip = 'Specifies a safety guard. The job refuses to close or re-close any fiscal year that starts before this date.';
        }
        field(30; "Auto-Create Next Fiscal Year"; Boolean)
        {
            Caption = 'Auto-Create Next Fiscal Year';
            ToolTip = 'Specifies whether the job creates the next fiscal year when no fiscal year starts after today. Business Central cannot close a year until the following year exists.';
        }
        field(31; "Period Length"; DateFormula)
        {
            Caption = 'Period Length';
            ToolTip = 'Specifies the length of each accounting period created by the job, for example 1M.';
        }
        field(32; "No. of Periods"; Integer)
        {
            Caption = 'No. of Periods';
            MinValue = 1;
            InitValue = 12;
            ToolTip = 'Specifies how many accounting periods make up a fiscal year created by the job.';
        }
        field(40; "Gen. Journal Template Name"; Code[10])
        {
            Caption = 'Gen. Journal Template Name';
            TableRelation = "Gen. Journal Template" where(Type = const(General), Recurring = const(false));
            ToolTip = 'Specifies the general journal template used for the closing entries.';

            trigger OnValidate()
            begin
                if "Gen. Journal Template Name" <> xRec."Gen. Journal Template Name" then
                    "Gen. Journal Batch Name" := '';
            end;
        }
        field(41; "Gen. Journal Batch Name"; Code[10])
        {
            Caption = 'Gen. Journal Batch Name';
            TableRelation = "Gen. Journal Batch".Name where("Journal Template Name" = field("Gen. Journal Template Name"));
            ToolTip = 'Specifies a dedicated journal batch for closing entries. It must be empty when the job runs. If it has a No. Series, the closing document takes the next number from it.';
        }
        field(42; "Retained Earnings Acc."; Code[20])
        {
            Caption = 'Retained Earnings Acc.';
            TableRelation = "G/L Account" where("Income/Balance" = const("Balance Sheet"), "Account Type" = const(Posting));
            ToolTip = 'Specifies the balance sheet account that receives the net result of the year.';
        }
        field(43; "Document No. Prefix"; Code[10])
        {
            Caption = 'Document No. Prefix';
            InitValue = 'CLOSE';
            ToolTip = 'Specifies the prefix of the closing document number when the journal batch has no No. Series. The calendar year of the fiscal year end date is appended, for example CLOSE2025.';
        }
        field(44; "Posting Description"; Text[100])
        {
            Caption = 'Posting Description';
            InitValue = 'Close Income Statement FY ending %1';
            ToolTip = 'Specifies the description of the closing entries. %1 is replaced with the fiscal year end date.';
        }
        field(50; "Close by Business Unit"; Boolean)
        {
            Caption = 'Close by Business Unit';
            ToolTip = 'Specifies whether closing entries are created per business unit code.';
        }
        field(51; "Close by Global Dimension 1"; Boolean)
        {
            Caption = 'Close by Global Dimension 1';
            ToolTip = 'Specifies whether closing entries are created per Global Dimension 1 value.';
        }
        field(52; "Close by Global Dimension 2"; Boolean)
        {
            Caption = 'Close by Global Dimension 2';
            ToolTip = 'Specifies whether closing entries are created per Global Dimension 2 value.';
        }
        field(60; "Post Automatically"; Boolean)
        {
            Caption = 'Post Automatically';
            ToolTip = 'Specifies whether the closing journal is posted by the job. When off, the lines are left in the batch for review and manual posting.';
        }
        field(61; "Re-close Lookback (Years)"; Integer)
        {
            Caption = 'Re-close Lookback (Years)';
            MinValue = 1;
            InitValue = 1;
            ToolTip = 'Specifies how many of the most recent closed fiscal years are re-checked on every run. Late postings into a closed year are transferred to retained earnings as a delta.';
        }
        field(70; "Open Posting Window"; Boolean)
        {
            Caption = 'Open Posting Window';
            InitValue = true;
            ToolTip = 'Specifies whether the closing journal is allowed to post without anything being left open. While it posts, the running user''s Allow Posting From/To in User Setup is set to the closing date alone, and blocked dimension values used by the closing lines are unblocked. Both are put back straight after.';
        }
        field(71; "Window User ID"; Code[50])
        {
            Caption = 'Posting Window Open For';
            DataClassification = EndUserIdentifiableInformation;
            Editable = false;
            ToolTip = 'Specifies the user whose posting dates are temporarily changed. Blank when no posting window is open.';
        }
        field(72; "Window Saved From"; Date)
        {
            Caption = 'Saved Allow Posting From';
            Editable = false;
            ToolTip = 'Specifies the Allow Posting From date that is put back when the posting window closes.';
        }
        field(73; "Window Saved To"; Date)
        {
            Caption = 'Saved Allow Posting To';
            Editable = false;
            ToolTip = 'Specifies the Allow Posting To date that is put back when the posting window closes.';
        }
        field(74; "Window Opened At"; DateTime)
        {
            Caption = 'Posting Window Opened At';
            Editable = false;
            ToolTip = 'Specifies when the posting window was opened.';
        }
        field(80; "Target Fiscal Year End"; Date)
        {
            Caption = 'Target Fiscal Year End';
            ToolTip = 'Specifies the end date of the one fiscal year a run may act on. When filled in, the run closes only that year, creates and posts only its closing journal, and never touches a later year. It stops instead of guessing if an earlier year is still open or the year has not ended. Leave blank for the automatic daily job.';
        }
    }

    keys
    {
        key(PK; "Primary Key") { Clustered = true; }
    }

    procedure GetSetup()
    begin
        if Get() then
            exit;
        Init();
        Evaluate("Period Length", '<1M>');
        Insert();
    end;

    procedure CheckJournalSetup()
    var
        GenJnlTemplate: Record "Gen. Journal Template";
        GenJnlBatch: Record "Gen. Journal Batch";
        GLAccount: Record "G/L Account";
    begin
        TestField("Gen. Journal Template Name");
        TestField("Gen. Journal Batch Name");
        TestField("Retained Earnings Acc.");
        TestField("Document No. Prefix");

        GenJnlTemplate.Get("Gen. Journal Template Name");
        GenJnlTemplate.TestField(Type, GenJnlTemplate.Type::General);
        GenJnlTemplate.TestField(Recurring, false);

        GenJnlBatch.Get("Gen. Journal Template Name", "Gen. Journal Batch Name");

        GLAccount.Get("Retained Earnings Acc.");
        GLAccount.TestField("Account Type", GLAccount."Account Type"::Posting);
        GLAccount.TestField("Income/Balance", GLAccount."Income/Balance"::"Balance Sheet");
        GLAccount.TestField(Blocked, false);
    end;
}
