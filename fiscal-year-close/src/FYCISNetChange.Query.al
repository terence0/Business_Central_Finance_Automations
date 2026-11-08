query 68300 "FYC IS Net Change"
{
    Caption = 'Income Statement Net Change';
    QueryType = Normal;
    Access = Internal;

    elements
    {
        dataitem(GLAccount; "G/L Account")
        {
            DataItemTableFilter = "Income/Balance" = const("Income Statement"), "Account Type" = const(Posting);
            column(GLAccountNo; "No.") { }

            dataitem(GLEntry; "G/L Entry")
            {
                DataItemLink = "G/L Account No." = GLAccount."No.";
                SqlJoinType = InnerJoin;

                filter(PostingDate; "Posting Date") { }
                column(BusinessUnitCode; "Business Unit Code") { }
                column(GlobalDim1Code; "Global Dimension 1 Code") { }
                column(GlobalDim2Code; "Global Dimension 2 Code") { }
                column(Amount; Amount) { Method = Sum; }
                column(AddCurrencyAmount; "Additional-Currency Amount") { Method = Sum; }
            }
        }
    }
}
