permissionset 68218 "CON User Perm Export"
{
    Assignable = true;
    Caption = 'CON User Permission Export';

    Permissions =
        tabledata "Access Control" = R,
        tabledata User = R,
        page "CON User Permission Sets" = X;
}
