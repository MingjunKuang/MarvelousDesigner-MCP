"""Conservative preflight advice; not a sandbox for arbitrary Python."""
import ast

SAFE = {'GetPatternCount','GetPatternInformation','GetPatternPieceName','GetLineLength',
        'GetSeamlinePairGroupCount','GetSeamlinePairGroupName','GetFabricCount','GetFabricName',
        'CreatePatternWithPoints','AddSeamlinePairGroup','MovePatternPoint','Simulate',
        'AssignFabricToPattern','ExportPatternJSON'}
POTENTIALLY_MODAL = {'NewProject','ImportFile','ImportFileW','ImportZPrj','ImportZPrjW','ImportAvatar'}
UNSAFE = {'Exit','Quit','ShowMessageBox','OpenFileDialog','SaveFileDialog'}

def classify(name, positional_count=None):
    name=name.rsplit('.',1)[-1]
    if name in UNSAFE:
        return 'unsafe'
    if name in POTENTIALLY_MODAL:
        return 'potentially_modal'
    if name in {'ExportOBJ','ExportOBJW','ExportFBX','ExportFBXW'}:
        return 'safe_with_explicit_options' if positional_count == 2 else 'potentially_modal'
    if name in {'ExportZPrj','ExportZPrjW'}:
        return 'safe_with_explicit_path' if positional_count in {1,2} else 'unknown'
    return 'safe' if name in SAFE else 'unknown'

def preflight(code):
    tree=ast.parse(code)
    calls=[]
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            name=ast.unparse(n.func)
            calls.append({'call':name,'classification':classify(name,len(n.args))})
    blocked=[c for c in calls if c['classification'] in {'unsafe','potentially_modal'}]
    return {'calls':calls,'blocked':blocked,'limitations':'Static advice only. Aliases, dynamic calls and option contents require review.'}
