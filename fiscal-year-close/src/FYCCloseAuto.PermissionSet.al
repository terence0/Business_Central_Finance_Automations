permissionset 68300 "FYC CLOSE AUTO"
{
    Caption = 'Fiscal Year Close Automation';
    Assignable = true;

    Permissions =
        tabledata "FYC Close Setup" = RIMD,
        tabledata "FYC Close Log" = RIMD,
        // Indirect only: posting dates can be changed through this extension's objects, not directly.
        tabledata "User Setup" = rim,
        tabledata "Dimension Value" = rm,
        tabledata "Default Dimension" = rm,
        tabledata "FYC Unblocked Dim. Value" = RIMD,
        tabledata "FYC Relaxed Default Dim." = RIMD,
        table "FYC Relaxed Default Dim." = X,
        table "FYC Close Setup" = X,
        table "FYC Unblocked Dim. Value" = X,
        table "FYC Close Log" = X,
        table "FYC Closing Buffer" = X,
        codeunit "FYC Close Management" = X,
        codeunit "FYC Job Queue Handler" = X,
        codeunit "FYC Posting Window" = X,
        codeunit "FYC Close Logger" = X,
        codeunit "FYC Close Runner" = X,
        page "FYC Close Setup" = X,
        page "FYC Close Log" = X,
        page "FYC Close Setup API" = X,
        page "FYC Close Log API" = X,
        page "FYC User Setup API" = X,
        query "FYC IS Net Change" = X;
}
