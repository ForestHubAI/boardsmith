# SPDX-License-Identifier: AGPL-3.0-or-later
"""VS Code Extension Generator — constraint visualization & diagnostics.

Generates a complete VS Code extension that:
  - Shows constraint solver results as VS Code diagnostics (Problems panel)
  - Provides CodeLens on board schema / intent YAML files
  - Renders a constraint report webview panel
  - Adds language support for boardsmith-fw YAML files

Usage:
    from boardsmith_fw.codegen.vscode_extension import generate_vscode_extension
    result = generate_vscode_extension(extension_name="boardsmith-fw")
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class VSCodeExtensionResult:
    files: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_vscode_extension(
    extension_name: str = "boardsmith-fw",
    publisher: str = "boardsmith-fw",
    display_name: str = "Eagle FW — Hardware-Aware Firmware Compiler",
) -> VSCodeExtensionResult:
    """Generate a complete VS Code extension project."""
    result = VSCodeExtensionResult()

    result.files.append(("package.json", _gen_package_json(
        extension_name, publisher, display_name,
    )))
    result.files.append(("tsconfig.json", _gen_tsconfig()))
    result.files.append((".vscodeignore", _gen_vscodeignore()))
    result.files.append(("src/extension.ts", _gen_extension_ts()))
    result.files.append(("src/diagnostics.ts", _gen_diagnostics_ts()))
    result.files.append(("src/codeLens.ts", _gen_codelens_ts()))
    result.files.append(("src/constraintPanel.ts", _gen_constraint_panel_ts()))
    result.files.append(("src/schemaValidator.ts", _gen_schema_validator_ts()))
    result.files.append(("syntaxes/board-schema.tmLanguage.json", _gen_tm_grammar()))
    result.files.append(("README.md", _gen_readme(display_name)))

    return result


# ---------------------------------------------------------------------------
# package.json
# ---------------------------------------------------------------------------


def _gen_package_json(name: str, publisher: str, display_name: str) -> str:
    return f"""\
{{
  "name": "{name}",
  "displayName": "{display_name}",
  "description": "Hardware-aware firmware compiler: constraint visualization, diagnostics, and code generation.",
  "version": "0.1.0",
  "publisher": "{publisher}",
  "engines": {{
    "vscode": "^1.85.0"
  }},
  "categories": ["Programming Languages", "Linters", "Visualization"],
  "activationEvents": [
    "workspaceContains:**/*.boardsmith-fw.yaml",
    "workspaceContains:**/board_schema.yaml",
    "workspaceContains:**/intent.yaml",
    "workspaceContains:**/topology.yaml"
  ],
  "main": "./out/extension.js",
  "contributes": {{
    "commands": [
      {{
        "command": "boardsmith-fw.runConstraints",
        "title": "Eagle FW: Run Constraint Solver"
      }},
      {{
        "command": "boardsmith-fw.showConstraintReport",
        "title": "Eagle FW: Show Constraint Report"
      }},
      {{
        "command": "boardsmith-fw.generateFirmware",
        "title": "Eagle FW: Generate Firmware"
      }},
      {{
        "command": "boardsmith-fw.validateSchema",
        "title": "Eagle FW: Validate Board Schema"
      }}
    ],
    "languages": [
      {{
        "id": "boardsmith-fw-board-schema",
        "aliases": ["Eagle FW Board Schema"],
        "filenames": ["board_schema.yaml"],
        "configuration": "./language-configuration.json"
      }},
      {{
        "id": "boardsmith-fw-intent",
        "aliases": ["Eagle FW Intent"],
        "filenames": ["intent.yaml"],
        "configuration": "./language-configuration.json"
      }}
    ],
    "grammars": [
      {{
        "language": "boardsmith-fw-board-schema",
        "scopeName": "source.boardsmith-fw.board-schema",
        "path": "./syntaxes/board-schema.tmLanguage.json"
      }}
    ],
    "configuration": {{
      "title": "Eagle FW",
      "properties": {{
        "boardsmith-fw.pythonPath": {{
          "type": "string",
          "default": "python3",
          "description": "Path to Python interpreter with boardsmith-fw installed"
        }},
        "boardsmith-fw.autoValidate": {{
          "type": "boolean",
          "default": true,
          "description": "Automatically validate board schemas on save"
        }},
        "boardsmith-fw.target": {{
          "type": "string",
          "default": "auto",
          "enum": ["auto", "esp32", "esp32c3", "stm32", "rp2040", "nrf52"],
          "description": "Default target MCU for code generation"
        }}
      }}
    }}
  }},
  "scripts": {{
    "vscode:prepublish": "npm run compile",
    "compile": "tsc -p ./",
    "watch": "tsc -watch -p ./",
    "lint": "eslint src --ext ts"
  }},
  "devDependencies": {{
    "@types/vscode": "^1.85.0",
    "@types/node": "^20.0.0",
    "typescript": "^5.3.0",
    "eslint": "^8.56.0",
    "@typescript-eslint/eslint-plugin": "^6.0.0",
    "@typescript-eslint/parser": "^6.0.0"
  }}
}}
"""


# ---------------------------------------------------------------------------
# tsconfig.json
# ---------------------------------------------------------------------------


def _gen_tsconfig() -> str:
    return """\
{
  "compilerOptions": {
    "module": "commonjs",
    "target": "ES2022",
    "outDir": "out",
    "lib": ["ES2022"],
    "sourceMap": true,
    "rootDir": "src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true
  },
  "exclude": ["node_modules", ".vscode-test"]
}
"""


# ---------------------------------------------------------------------------
# .vscodeignore
# ---------------------------------------------------------------------------


def _gen_vscodeignore() -> str:
    return """\
.vscode/**
.vscode-test/**
src/**
.gitignore
tsconfig.json
**/*.map
node_modules/**
"""


# ---------------------------------------------------------------------------
# src/extension.ts — main entry point
# ---------------------------------------------------------------------------


def _gen_extension_ts() -> str:
    return """\
import * as vscode from 'vscode';
import { ConstraintDiagnosticProvider } from './diagnostics';
import { EagleFWCodeLensProvider } from './codeLens';
import { ConstraintPanel } from './constraintPanel';
import { SchemaValidator } from './schemaValidator';

let diagnosticProvider: ConstraintDiagnosticProvider;

export function activate(context: vscode.ExtensionContext) {
    console.log('boardsmith-fw extension activated');

    // Diagnostic provider — shows constraint errors in Problems panel
    diagnosticProvider = new ConstraintDiagnosticProvider(context);

    // CodeLens — inline actions on board schema files
    const codeLensProvider = new EagleFWCodeLensProvider();
    context.subscriptions.push(
        vscode.languages.registerCodeLensProvider(
            { pattern: '**/board_schema.yaml' },
            codeLensProvider
        ),
        vscode.languages.registerCodeLensProvider(
            { pattern: '**/intent.yaml' },
            codeLensProvider
        ),
        vscode.languages.registerCodeLensProvider(
            { pattern: '**/topology.yaml' },
            codeLensProvider
        )
    );

    // Schema validator
    const validator = new SchemaValidator();

    // Commands
    context.subscriptions.push(
        vscode.commands.registerCommand('boardsmith-fw.runConstraints', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) {
                vscode.window.showWarningMessage('No active editor');
                return;
            }
            await diagnosticProvider.runConstraints(editor.document.uri);
        }),

        vscode.commands.registerCommand('boardsmith-fw.showConstraintReport', () => {
            ConstraintPanel.createOrShow(context.extensionUri);
        }),

        vscode.commands.registerCommand('boardsmith-fw.generateFirmware', async () => {
            const config = vscode.workspace.getConfiguration('boardsmith-fw');
            const pythonPath = config.get<string>('pythonPath', 'python3');
            const target = config.get<string>('target', 'auto');

            const terminal = vscode.window.createTerminal('Eagle FW');
            terminal.show();
            terminal.sendText(
                `${pythonPath} -m boardsmith_fw.cli generate --target ${target}`
            );
        }),

        vscode.commands.registerCommand('boardsmith-fw.validateSchema', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) {
                vscode.window.showWarningMessage('No active editor');
                return;
            }
            const issues = await validator.validate(editor.document);
            if (issues.length === 0) {
                vscode.window.showInformationMessage(
                    'Board schema is valid'
                );
            }
        })
    );

    // Auto-validate on save
    context.subscriptions.push(
        vscode.workspace.onDidSaveTextDocument(async (doc) => {
            const config = vscode.workspace.getConfiguration('boardsmith-fw');
            if (!config.get<boolean>('autoValidate', true)) {
                return;
            }
            const fileName = doc.fileName;
            if (
                fileName.endsWith('board_schema.yaml') ||
                fileName.endsWith('intent.yaml') ||
                fileName.endsWith('topology.yaml')
            ) {
                await diagnosticProvider.runConstraints(doc.uri);
            }
        })
    );
}

export function deactivate() {
    if (diagnosticProvider) {
        diagnosticProvider.dispose();
    }
}
"""


# ---------------------------------------------------------------------------
# src/diagnostics.ts — constraint solver → VS Code diagnostics
# ---------------------------------------------------------------------------


def _gen_diagnostics_ts() -> str:
    return """\
import * as vscode from 'vscode';
import { execFile } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);

interface ConstraintResult {
    id: string;
    category: string;
    description: string;
    severity: 'error' | 'warning' | 'info';
    status: 'pass' | 'fail' | 'unknown';
    affected_components: string[];
}

interface ConstraintReport {
    summary: {
        total: number;
        pass: number;
        fail: number;
        unknown: number;
        errors: number;
        warnings: number;
        valid: boolean;
    };
    categories: Record<string, ConstraintResult[]>;
}

export class ConstraintDiagnosticProvider {
    private diagnosticCollection: vscode.DiagnosticCollection;
    private statusBarItem: vscode.StatusBarItem;

    constructor(context: vscode.ExtensionContext) {
        this.diagnosticCollection = vscode.languages.createDiagnosticCollection(
            'boardsmith-fw'
        );
        context.subscriptions.push(this.diagnosticCollection);

        this.statusBarItem = vscode.window.createStatusBarItem(
            vscode.StatusBarAlignment.Left, 100
        );
        this.statusBarItem.command = 'boardsmith-fw.showConstraintReport';
        context.subscriptions.push(this.statusBarItem);
    }

    async runConstraints(uri: vscode.Uri): Promise<void> {
        const config = vscode.workspace.getConfiguration('boardsmith-fw');
        const pythonPath = config.get<string>('pythonPath', 'python3');
        const workDir = vscode.workspace.getWorkspaceFolder(uri)?.uri.fsPath;

        if (!workDir) {
            vscode.window.showErrorMessage('No workspace folder found');
            return;
        }

        try {
            this.statusBarItem.text = '$(loading~spin) Eagle FW: analyzing...';
            this.statusBarItem.show();

            const { stdout } = await execFileAsync(pythonPath, [
                '-m', 'boardsmith_fw.cli', 'report',
                '--out', workDir,
                '--format', 'json'
            ], { cwd: workDir, timeout: 30000 });

            const report: ConstraintReport = JSON.parse(stdout);
            this.updateDiagnostics(uri, report);
            this.updateStatusBar(report);
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : String(err);
            vscode.window.showErrorMessage(
                `Eagle FW constraint solver failed: ${msg}`
            );
            this.statusBarItem.text = '$(error) Eagle FW: error';
        }
    }

    private updateDiagnostics(
        uri: vscode.Uri,
        report: ConstraintReport
    ): void {
        const diagnostics: vscode.Diagnostic[] = [];

        for (const [category, constraints] of Object.entries(report.categories)) {
            for (const c of constraints) {
                if (c.status === 'pass') {
                    continue;
                }

                const severity = c.severity === 'error'
                    ? vscode.DiagnosticSeverity.Error
                    : c.severity === 'warning'
                    ? vscode.DiagnosticSeverity.Warning
                    : vscode.DiagnosticSeverity.Information;

                const diag = new vscode.Diagnostic(
                    new vscode.Range(0, 0, 0, 0),
                    `[${category}] ${c.description}`,
                    severity
                );
                diag.source = 'boardsmith-fw';
                diag.code = c.id;
                diagnostics.push(diag);
            }
        }

        this.diagnosticCollection.set(uri, diagnostics);
    }

    private updateStatusBar(report: ConstraintReport): void {
        const s = report.summary;
        if (s.valid) {
            this.statusBarItem.text =
                `$(check) Eagle FW: ${s.pass}/${s.total} pass`;
            this.statusBarItem.backgroundColor = undefined;
        } else {
            this.statusBarItem.text =
                `$(error) Eagle FW: ${s.errors} errors, ${s.warnings} warnings`;
            this.statusBarItem.backgroundColor =
                new vscode.ThemeColor('statusBarItem.errorBackground');
        }
        this.statusBarItem.show();
    }

    dispose(): void {
        this.diagnosticCollection.dispose();
        this.statusBarItem.dispose();
    }
}
"""


# ---------------------------------------------------------------------------
# src/codeLens.ts — inline actions on YAML files
# ---------------------------------------------------------------------------


def _gen_codelens_ts() -> str:
    return """\
import * as vscode from 'vscode';

export class EagleFWCodeLensProvider implements vscode.CodeLensProvider {

    provideCodeLenses(
        document: vscode.TextDocument,
        _token: vscode.CancellationToken
    ): vscode.CodeLens[] {
        const lenses: vscode.CodeLens[] = [];
        const firstLine = new vscode.Range(0, 0, 0, 0);
        const fileName = document.fileName;

        if (fileName.endsWith('board_schema.yaml')) {
            lenses.push(
                new vscode.CodeLens(firstLine, {
                    title: '$(circuit-board) Validate Board Schema',
                    command: 'boardsmith-fw.validateSchema',
                    tooltip: 'Run constraint solver on this board schema',
                }),
                new vscode.CodeLens(firstLine, {
                    title: '$(gear) Generate Firmware',
                    command: 'boardsmith-fw.generateFirmware',
                    tooltip: 'Generate firmware from this board schema',
                }),
                new vscode.CodeLens(firstLine, {
                    title: '$(graph) Show Constraints',
                    command: 'boardsmith-fw.showConstraintReport',
                    tooltip: 'Show constraint report in panel',
                })
            );
        }

        if (fileName.endsWith('intent.yaml')) {
            lenses.push(
                new vscode.CodeLens(firstLine, {
                    title: '$(play) Compile Intent',
                    command: 'boardsmith-fw.generateFirmware',
                    tooltip: 'Compile this intent into firmware',
                })
            );

            // Add lens on each task definition
            for (let i = 0; i < document.lineCount; i++) {
                const line = document.lineAt(i);
                const match = line.text.match(/^\\s+- name:\\s+(.+)/);
                if (match) {
                    const taskName = match[1].trim();
                    lenses.push(
                        new vscode.CodeLens(line.range, {
                            title: `$(symbol-event) Task: ${taskName}`,
                            command: '',
                            tooltip: `Firmware task: ${taskName}`,
                        })
                    );
                }
            }
        }

        if (fileName.endsWith('topology.yaml')) {
            lenses.push(
                new vscode.CodeLens(firstLine, {
                    title: '$(globe) Compile Topology',
                    command: 'boardsmith-fw.generateFirmware',
                    tooltip: 'Generate multi-board communication code',
                })
            );

            // Annotate each node
            for (let i = 0; i < document.lineCount; i++) {
                const line = document.lineAt(i);
                const match = line.text.match(/^\\s+- name:\\s+(.+)/);
                if (match) {
                    const nodeName = match[1].trim();
                    lenses.push(
                        new vscode.CodeLens(line.range, {
                            title: `$(server) Node: ${nodeName}`,
                            command: '',
                            tooltip: `Board node: ${nodeName}`,
                        })
                    );
                }
            }
        }

        return lenses;
    }
}
"""


# ---------------------------------------------------------------------------
# src/constraintPanel.ts — webview panel for constraint visualization
# ---------------------------------------------------------------------------


def _gen_constraint_panel_ts() -> str:
    return """\
import * as vscode from 'vscode';
import { execFile } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);

export class ConstraintPanel {
    public static currentPanel: ConstraintPanel | undefined;
    private readonly panel: vscode.WebviewPanel;
    private disposables: vscode.Disposable[] = [];

    public static createOrShow(extensionUri: vscode.Uri): void {
        const column = vscode.ViewColumn.Two;

        if (ConstraintPanel.currentPanel) {
            ConstraintPanel.currentPanel.panel.reveal(column);
            ConstraintPanel.currentPanel.refresh();
            return;
        }

        const panel = vscode.window.createWebviewPanel(
            'eagleFwConstraints',
            'Eagle FW Constraints',
            column,
            { enableScripts: true }
        );

        ConstraintPanel.currentPanel = new ConstraintPanel(panel);
    }

    private constructor(panel: vscode.WebviewPanel) {
        this.panel = panel;
        this.panel.onDidDispose(() => this.dispose(), null, this.disposables);
        this.refresh();
    }

    async refresh(): Promise<void> {
        const config = vscode.workspace.getConfiguration('boardsmith-fw');
        const pythonPath = config.get<string>('pythonPath', 'python3');
        const folders = vscode.workspace.workspaceFolders;

        if (!folders || folders.length === 0) {
            this.panel.webview.html = this.getErrorHtml(
                'No workspace folder open'
            );
            return;
        }

        const workDir = folders[0].uri.fsPath;

        try {
            const { stdout } = await execFileAsync(pythonPath, [
                '-m', 'boardsmith_fw.cli', 'report',
                '--out', workDir,
                '--format', 'html'
            ], { cwd: workDir, timeout: 30000 });

            this.panel.webview.html = stdout;
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : String(err);
            this.panel.webview.html = this.getErrorHtml(msg);
        }
    }

    private getErrorHtml(message: string): string {
        return `<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: sans-serif; padding: 2rem;">
<h2>Eagle FW — Constraint Report</h2>
<p style="color: #c00;">Could not generate report: ${message}</p>
<p>Make sure you have:</p>
<ul>
    <li>Run <code>boardsmith-fw analyze</code> to create hardware_graph.json</li>
    <li>Set the correct Python path in settings</li>
</ul>
</body>
</html>`;
    }

    private dispose(): void {
        ConstraintPanel.currentPanel = undefined;
        this.panel.dispose();
        while (this.disposables.length) {
            const d = this.disposables.pop();
            if (d) { d.dispose(); }
        }
    }
}
"""


# ---------------------------------------------------------------------------
# src/schemaValidator.ts — validate board schema structure
# ---------------------------------------------------------------------------


def _gen_schema_validator_ts() -> str:
    return """\
import * as vscode from 'vscode';

interface ValidationIssue {
    line: number;
    message: string;
    severity: vscode.DiagnosticSeverity;
}

export class SchemaValidator {
    private diagnosticCollection: vscode.DiagnosticCollection;

    constructor() {
        this.diagnosticCollection = vscode.languages.createDiagnosticCollection(
            'boardsmith-fw-schema'
        );
    }

    async validate(document: vscode.TextDocument): Promise<ValidationIssue[]> {
        const text = document.getText();
        const issues: ValidationIssue[] = [];
        const diagnostics: vscode.Diagnostic[] = [];

        const lines = text.split('\\n');

        // Check required top-level keys for board schema
        if (document.fileName.endsWith('board_schema.yaml')) {
            const hasVersion = lines.some(l => l.match(/^eagle_board_schema:/));
            if (!hasVersion) {
                issues.push({
                    line: 0,
                    message: 'Missing required key: eagle_board_schema (version)',
                    severity: vscode.DiagnosticSeverity.Error,
                });
            }

            const hasMcu = lines.some(l => l.match(/^\\s+mcu:/));
            if (!hasMcu) {
                issues.push({
                    line: 0,
                    message: 'Missing required key: mcu',
                    severity: vscode.DiagnosticSeverity.Error,
                });
            }

            // Check for common mistakes
            for (let i = 0; i < lines.length; i++) {
                const line = lines[i];

                // Check I2C address format
                const addrMatch = line.match(/address:\\s*(.+)/);
                if (addrMatch) {
                    const addr = addrMatch[1].trim();
                    if (!addr.match(/^0x[0-9a-fA-F]+$/)) {
                        issues.push({
                            line: i,
                            message: `I2C address should be hex (e.g. 0x76), got: ${addr}`,
                            severity: vscode.DiagnosticSeverity.Warning,
                        });
                    }
                }

                // Check bus type validity
                const busMatch = line.match(/bus:\\s*(\\w+)/);
                if (busMatch) {
                    const bus = busMatch[1].toUpperCase();
                    const validBuses = ['I2C', 'SPI', 'UART', 'ADC', 'PWM', 'CAN'];
                    if (!validBuses.includes(bus)) {
                        issues.push({
                            line: i,
                            message: `Unknown bus type: ${busMatch[1]}. Valid: ${validBuses.join(', ')}`,
                            severity: vscode.DiagnosticSeverity.Warning,
                        });
                    }
                }
            }
        }

        // Check intent YAML
        if (document.fileName.endsWith('intent.yaml')) {
            const hasVersion = lines.some(l => l.match(/^boardsmith_fw_intent:/));
            if (!hasVersion) {
                issues.push({
                    line: 0,
                    message: 'Missing required key: boardsmith_fw_intent (version)',
                    severity: vscode.DiagnosticSeverity.Error,
                });
            }

            const hasFirmware = lines.some(l => l.match(/^firmware:/));
            if (!hasFirmware) {
                issues.push({
                    line: 0,
                    message: 'Missing required key: firmware',
                    severity: vscode.DiagnosticSeverity.Error,
                });
            }
        }

        // Convert to VS Code diagnostics
        for (const issue of issues) {
            const range = new vscode.Range(issue.line, 0, issue.line, 1000);
            const diag = new vscode.Diagnostic(range, issue.message, issue.severity);
            diag.source = 'boardsmith-fw';
            diagnostics.push(diag);
        }

        this.diagnosticCollection.set(document.uri, diagnostics);
        return issues;
    }
}
"""


# ---------------------------------------------------------------------------
# TextMate grammar for board schema YAML
# ---------------------------------------------------------------------------


def _gen_tm_grammar() -> str:
    return """\
{
  "scopeName": "source.boardsmith-fw.board-schema",
  "patterns": [
    {
      "match": "^(eagle_board_schema|boardsmith_fw_intent):",
      "name": "keyword.control.boardsmith-fw"
    },
    {
      "match": "\\\\b(mcu|components|buses|power|pins|bus|address|interface):",
      "name": "entity.name.tag.boardsmith-fw"
    },
    {
      "match": "\\\\b(I2C|SPI|UART|ADC|PWM|CAN|GPIO)\\\\b",
      "name": "constant.language.boardsmith-fw"
    },
    {
      "match": "0x[0-9a-fA-F]+",
      "name": "constant.numeric.hex.boardsmith-fw"
    },
    {
      "match": "\\\\b(ESP32|ESP32-C3|STM32|RP2040|NRF52|BME280|SSD1306|W25Q128)\\\\b",
      "name": "entity.name.type.boardsmith-fw"
    },
    {
      "match": "#.*$",
      "name": "comment.line.number-sign.boardsmith-fw"
    },
    {
      "match": "\\\\b(every|trigger|read|actions|store_as|values):",
      "name": "keyword.other.boardsmith-fw"
    }
  ]
}
"""


# ---------------------------------------------------------------------------
# README.md
# ---------------------------------------------------------------------------


def _gen_readme(display_name: str) -> str:
    return f"""\
# {display_name}

VS Code extension for the boardsmith-fw hardware-aware firmware compiler.

## Features

### Constraint Diagnostics
Constraint solver results appear directly in the **Problems** panel:
- Voltage mismatches, I2C address conflicts, bus capacitance violations
- Rise-time warnings, init sequence ordering issues
- Power sequencing errors

### CodeLens
Inline actions on your YAML files:
- **board_schema.yaml**: Validate, Generate Firmware, Show Constraints
- **intent.yaml**: Compile Intent, Task annotations
- **topology.yaml**: Compile Topology, Node annotations

### Constraint Report Panel
Interactive webview panel showing the full constraint report with:
- Pass/fail summary cards
- Per-category constraint table
- Color-coded severity indicators

### Schema Validation
Real-time validation of board schema and intent YAML files:
- Required key checks
- I2C address format validation
- Bus type validation

## Requirements

- Python 3.10+ with `boardsmith-fw` installed
- `boardsmith-fw analyze` must be run first to create `hardware_graph.json`

## Extension Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `boardsmith-fw.pythonPath` | `python3` | Path to Python interpreter |
| `boardsmith-fw.autoValidate` | `true` | Auto-validate on save |
| `boardsmith-fw.target` | `auto` | Default target MCU |

## Commands

- **Eagle FW: Run Constraint Solver** — Analyze hardware and show diagnostics
- **Eagle FW: Show Constraint Report** — Open constraint report panel
- **Eagle FW: Generate Firmware** — Generate firmware for current board
- **Eagle FW: Validate Board Schema** — Validate YAML structure
"""
