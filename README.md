Macro pouir préparation des documents : conversion des numérotations EXG_ :

Sub ConvertEXGListNumbersToText_MultiLevel()
Dim p As Paragraph
Dim lbl As String
Dim i As Long

Application.ScreenUpdating = False

For i = ActiveDocument.Paragraphs.Count To 1 Step -1
Set p = ActiveDocument.Paragraphs(i)
On Error Resume Next
If p.Range.ListFormat.ListType <> wdListNoNumbering Then
lbl = p.Range.ListFormat.ListString
If Len(lbl) > 0 Then
' Nettoyage basique : enlever tabulations / NBSP et espaces superflus
lbl = Replace(lbl, vbTab, "")
lbl = Replace(lbl, Chr(9), "")
lbl = Replace(lbl, Chr(160), " ")
lbl = Trim(lbl)
' Retirer ponctuation résiduelle en fin (., ), :)
Do While Len(lbl) > 0 And (Right(lbl, 1) = "." Or Right(lbl, 1) = ":" Or Right(lbl, 1) = ")" )
lbl = Left(lbl, Len(lbl) - 1)
lbl = Trim(lbl)
Loop
' Tester si commence par "EXG" (insensible à la casse)
If Len(lbl) >= 3 And UCase(Left(lbl, 3)) = "EXG" Then
' Retirer la numérotation du paragraphe
p.Range.ListFormat.RemoveNumbers
' Insérer le libellé comme texte fixe avant le paragraphe
p.Range.InsertBefore lbl & " "
End If
End If
End If
On Error GoTo 0
Next i

Application.ScreenUpdating = True
MsgBox "Conversion terminée pour les labels commençant par 'EXG'."
End Sub
