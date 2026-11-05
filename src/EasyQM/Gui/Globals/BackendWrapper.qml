pragma Singleton

import QtQuick

import Backends as Backends

// Wrapper to the Python backend API, exposing its properties and methods to the QML GUI.
// - In GUI code, backend properties and methods MUST be accessed through this object.
// - Flat structure: the backend part is encoded in the name (projectName = backend.project.name).
// - Writable properties get a setter function; assigning them from QML would break the binding.

QtObject {

    readonly property var activeBackend: Backends.PyBackend

    /////////////////////////////////////////////
    // Whole application (the app bar Reset button)
    /////////////////////////////////////////////
    // Whether a reset would discard work: edits since start-up or the last reset that no
    // saved project file holds
    readonly property bool edited: activeBackend.edited
    // Everything back to start-up: no project, the benzene sample, default calculations and
    // method, no job or results; refused while a job runs
    function reset() { activeBackend.reset() }

    ///////////////
    // Project page
    ///////////////
    readonly property bool projectCreated: activeBackend.project.created
    readonly property string projectLocation: activeBackend.project.location
    readonly property string projectParentDirectory: activeBackend.project.parentDirectory
    readonly property string projectCreatedAt: activeBackend.project.createdAt
    readonly property string projectModifiedAt: activeBackend.project.modifiedAt
    readonly property string projectSampleName: activeBackend.project.sampleName
    readonly property var projectCalculations: activeBackend.project.calculations
    readonly property string projectEngine: activeBackend.project.engine
    readonly property string projectStatus: activeBackend.project.status
    readonly property string projectStatusLabel: activeBackend.project.statusLabel
    readonly property string projectLastSaved: activeBackend.project.lastSaved
    readonly property bool projectHasUnsavedChanges: activeBackend.project.hasUnsavedChanges

    readonly property string projectName: activeBackend.project.name
    function projectSetName(value) { activeBackend.project.setName(value) }
    readonly property string projectDescription: activeBackend.project.description
    function projectSetDescription(value) { activeBackend.project.setDescription(value) }
    function projectSetLocation(value) { activeBackend.project.setLocation(value) }
    readonly property bool projectAutoSave: activeBackend.project.autoSave
    function projectSetAutoSave(value) { activeBackend.project.setAutoSave(value) }

    function projectCreate() { activeBackend.project.create() }
    function projectSave() { activeBackend.project.save() }
    function projectLoad(path) { activeBackend.project.load(path) }

    //////////////
    // Sample page
    //////////////
    readonly property string sampleName: activeBackend.sample.name
    readonly property string sampleSource: activeBackend.sample.source
    readonly property string sampleFormula: activeBackend.sample.formula
    readonly property string sampleSummary: activeBackend.sample.summary
    readonly property int sampleAtomCount: activeBackend.sample.atomCount
    readonly property bool samplePeriodic: activeBackend.sample.periodic
    // {a, b, c, alpha, beta, gamma, volume, spaceGroup, vectors}; empty for a molecule
    readonly property var sampleCell: activeBackend.sample.cell
    // Schoenflies symbol of a molecule; empty for a crystal or above samplePointGroupAtomLimit atoms
    readonly property string samplePointGroup: activeBackend.sample.pointGroup
    readonly property int samplePointGroupAtomLimit: activeBackend.sample.pointGroupAtomLimit
    readonly property int sampleCharge: activeBackend.sample.charge
    readonly property int sampleMultiplicity: activeBackend.sample.multiplicity
    // [{value, label}] of the multiplicities the electron count allows
    readonly property var sampleMultiplicityChoices: activeBackend.sample.multiplicityChoices
    // A multiplicity the new charge does not allow goes to the lowest allowed one
    function sampleSetCharge(value) { activeBackend.sample.setCharge(value) }
    function sampleSetMultiplicity(value) { activeBackend.sample.setMultiplicity(value) }
    readonly property var sampleAtoms: activeBackend.sample.atoms
    readonly property int sampleFixedCount: activeBackend.sample.fixedCount
    // On a selected atom, fixes or frees every selected atom
    function sampleSetAtomFixed(index, value) { activeBackend.sample.setAtomFixed(index, value) }
    // XYZ (extended XYZ with a cell) or CIF
    function sampleLoadStructure(path) { activeBackend.sample.loadStructure(path) }
    // Edits, as typed: axis 0, 1, 2 in the coordinates the tables show; name 'a' … 'gamma'.
    // Text that is not a number, or makes no cell, changes nothing.
    function sampleSetAtomCoordinate(index, axis, text) { activeBackend.sample.setAtomCoordinate(index, axis, text) }
    function sampleSetCellParameter(name, text) { activeBackend.sample.setCellParameter(name, text) }
    // Cartesian x, y, z in Å, from the viewer's atom mover
    function sampleSetAtomPosition(index, x, y, z) { activeBackend.sample.setAtomPosition(index, x, y, z) }
    // A carbon at the origin (fractional [0, 0, 0] in a crystal), then selected; removing
    // every atom is refused
    function sampleAddAtom() { activeBackend.sample.addAtom() }
    function sampleRemoveSelectedAtoms() { activeBackend.sample.removeSelectedAtoms() }
    // What the viewer draws: atoms with copies in other cells, bonds between them, cell edges
    readonly property var sampleSceneAtoms: activeBackend.sample.sceneAtoms
    readonly property var sampleSceneBonds: activeBackend.sample.sceneBonds
    readonly property var sampleCellEdges: activeBackend.sample.cellEdges
    readonly property var sampleSceneCentre: activeBackend.sample.sceneCentre
    readonly property real sampleSceneExtent: activeBackend.sample.sceneExtent
    readonly property int sampleSceneAtomLimit: activeBackend.sample.sceneAtomLimit
    // Display settings
    readonly property var sampleViewRepeat: activeBackend.sample.viewRepeat
    function sampleSetViewRepeat(na, nb, nc) { activeBackend.sample.setViewRepeat(na, nb, nc) }
    readonly property bool sampleViewBoundaryAtoms: activeBackend.sample.viewBoundaryAtoms
    function sampleSetViewBoundaryAtoms(value) { activeBackend.sample.setViewBoundaryAtoms(value) }
    // 'cartesian' | 'fractional' (crystal) | 'zmatrix' (molecule), for the atom tables
    readonly property string sampleCoordinates: activeBackend.sample.coordinates
    function sampleSetCoordinates(value) { activeBackend.sample.setCoordinates(value) }
    // Z-matrix rows in construction order, while shown: [{atom, label, element, bondTo, bond,
    // angleTo, angle, dihedralTo, dihedral}]; a reference '' is the origin or an axis
    readonly property var sampleZmatrix: activeBackend.sample.zmatrix
    // Why there is no Z-matrix to show (a linear molecule); '' otherwise
    readonly property string sampleZmatrixError: activeBackend.sample.zmatrixError
    // field 'bond' | 'angle' | 'dihedral', as typed; refused text changes nothing
    function sampleSetZmatrixValue(atom, field, text) { activeBackend.sample.setZmatrixValue(atom, field, text) }
    // Selected atom indices, shared by the viewer and the atom tables
    readonly property var sampleSelectedAtoms: activeBackend.sample.selectedAtoms
    // Indices into sampleSceneAtoms of the selected drawn atoms
    readonly property var sampleSelectedSceneAtoms: activeBackend.sample.selectedSceneAtoms
    readonly property string sampleSelectionText: activeBackend.sample.selectionText
    // Distance, angle or dihedral of 2, 3 or 4 selected atoms
    readonly property string sampleSelectionMeasurement: activeBackend.sample.selectionMeasurement
    // mode: 'only' (click), 'toggle' (Ctrl-click), 'range' (Shift-click)
    function sampleSelectAtom(index, mode) { activeBackend.sample.selectAtom(index, mode) }
    // The viewer's pick of a drawn atom; mode 'only' or 'toggle'
    function sampleSelectSceneAtom(sceneIndex, mode) { activeBackend.sample.selectSceneAtom(sceneIndex, mode) }
    function sampleClearSelection() { activeBackend.sample.clearSelection() }

    ////////////////////
    // Calculations page
    ////////////////////
    readonly property var calculationsRows: activeBackend.calculations.rows
    readonly property int calculationsSelectedCount: activeBackend.calculations.selectedCount
    readonly property var calculationsWorkflow: activeBackend.calculations.workflow
    function calculationsSetSelected(type, value) { activeBackend.calculations.setSelected(type, value) }

    readonly property bool calculationsSinglePointPrintOrbitals: activeBackend.calculations.singlePointPrintOrbitals
    function calculationsSetSinglePointPrintOrbitals(value) { activeBackend.calculations.setSinglePointPrintOrbitals(value) }
    readonly property string calculationsSinglePointGeometry: activeBackend.calculations.singlePointGeometry
    readonly property var calculationsSinglePointGeometryChoices: activeBackend.calculations.singlePointGeometryChoices
    function calculationsSetSinglePointGeometry(value) { activeBackend.calculations.setSinglePointGeometry(value) }

    readonly property string calculationsOptConvergence: activeBackend.calculations.optConvergence
    readonly property var calculationsOptConvergenceChoices: activeBackend.calculations.optConvergenceChoices
    function calculationsSetOptConvergence(value) { activeBackend.calculations.setOptConvergence(value) }
    readonly property int calculationsOptMaxSteps: activeBackend.calculations.optMaxSteps
    function calculationsSetOptMaxSteps(value) { activeBackend.calculations.setOptMaxSteps(value) }
    readonly property string calculationsOptOptimise: activeBackend.calculations.optOptimise
    readonly property var calculationsOptOptimiseChoices: activeBackend.calculations.optOptimiseChoices
    function calculationsSetOptOptimise(value) { activeBackend.calculations.setOptOptimise(value) }
    readonly property bool calculationsOptKeepTrajectory: activeBackend.calculations.optKeepTrajectory
    function calculationsSetOptKeepTrajectory(value) { activeBackend.calculations.setOptKeepTrajectory(value) }

    readonly property string calculationsFreqType: activeBackend.calculations.freqType
    readonly property var calculationsFreqTypeChoices: activeBackend.calculations.freqTypeChoices
    function calculationsSetFreqType(value) { activeBackend.calculations.setFreqType(value) }
    readonly property real calculationsFreqTemperature: activeBackend.calculations.freqTemperature
    function calculationsSetFreqTemperature(value) { activeBackend.calculations.setFreqTemperature(value) }
    readonly property real calculationsFreqPressure: activeBackend.calculations.freqPressure
    function calculationsSetFreqPressure(value) { activeBackend.calculations.setFreqPressure(value) }
    readonly property bool calculationsFreqRaman: activeBackend.calculations.freqRaman
    function calculationsSetFreqRaman(value) { activeBackend.calculations.setFreqRaman(value) }

    //////////////
    // Method page
    //////////////
    readonly property var methodEngines: activeBackend.method.engines
    readonly property string methodEngineName: activeBackend.method.engineName
    readonly property bool methodEngineFound: activeBackend.method.engineFound
    readonly property string methodEngineVersion: activeBackend.method.engineVersion
    readonly property string methodEnginePath: activeBackend.method.enginePath
    readonly property string methodEngineCardText: activeBackend.method.engineCardText
    readonly property string methodEngineExecutableFilter: activeBackend.method.engineExecutableFilter
    function methodRedetect() { activeBackend.method.redetect() }
    function methodSetEnginePath(value) { activeBackend.method.setEnginePath(value) }
    // Whether the engine runs this kind of system (molecule or crystal), and why not
    readonly property bool methodCanRun: activeBackend.method.canRun
    readonly property string methodCannotRunReason: activeBackend.method.cannotRunReason

    readonly property bool methodPeriodic: activeBackend.method.periodic
    readonly property real methodKpointSpacing: activeBackend.method.kpointSpacing
    function methodSetKpointSpacing(value) { activeBackend.method.setKpointSpacing(value) }
    // [n1, n2, n3]; [] for a molecule
    readonly property var methodKpointGrid: activeBackend.method.kpointGrid
    function methodSetKpointGrid(n1, n2, n3) { activeBackend.method.setKpointGrid(n1, n2, n3) }

    readonly property string methodFamily: activeBackend.method.family
    readonly property var methodFamilyChoices: activeBackend.method.familyChoices
    function methodSetFamily(value) { activeBackend.method.setFamily(value) }
    readonly property string methodFunctional: activeBackend.method.functional
    readonly property var methodFunctionalChoices: activeBackend.method.functionalChoices
    function methodSetFunctional(value) { activeBackend.method.setFunctional(value) }
    readonly property string methodDispersion: activeBackend.method.dispersion
    readonly property var methodDispersionChoices: activeBackend.method.dispersionChoices
    function methodSetDispersion(value) { activeBackend.method.setDispersion(value) }
    readonly property string methodBasisSet: activeBackend.method.basisSet
    readonly property var methodBasisSetChoices: activeBackend.method.basisSetChoices
    function methodSetBasisSet(value) { activeBackend.method.setBasisSet(value) }
    readonly property string methodAuxiliaryBasis: activeBackend.method.auxiliaryBasis
    readonly property var methodAuxiliaryBasisChoices: activeBackend.method.auxiliaryBasisChoices
    function methodSetAuxiliaryBasis(value) { activeBackend.method.setAuxiliaryBasis(value) }

    readonly property string methodReference: activeBackend.method.reference
    readonly property var methodReferenceChoices: activeBackend.method.referenceChoices
    function methodSetReference(value) { activeBackend.method.setReference(value) }
    readonly property string methodSolvation: activeBackend.method.solvation
    readonly property var methodSolvationChoices: activeBackend.method.solvationChoices
    function methodSetSolvation(value) { activeBackend.method.setSolvation(value) }
    readonly property string methodOccupations: activeBackend.method.occupations
    readonly property var methodOccupationsChoices: activeBackend.method.occupationsChoices
    function methodSetOccupations(value) { activeBackend.method.setOccupations(value) }

    readonly property string methodScfConvergence: activeBackend.method.scfConvergence
    readonly property var methodScfConvergenceChoices: activeBackend.method.scfConvergenceChoices
    function methodSetScfConvergence(value) { activeBackend.method.setScfConvergence(value) }
    readonly property int methodScfMaxIterations: activeBackend.method.scfMaxIterations
    function methodSetScfMaxIterations(value) { activeBackend.method.setScfMaxIterations(value) }
    readonly property string methodIntegrationGrid: activeBackend.method.integrationGrid
    readonly property var methodIntegrationGridChoices: activeBackend.method.integrationGridChoices
    function methodSetIntegrationGrid(value) { activeBackend.method.setIntegrationGrid(value) }
    readonly property bool methodStabilityCheck: activeBackend.method.stabilityCheck
    readonly property bool methodStabilityCheckOffered: activeBackend.method.stabilityCheckOffered
    function methodSetStabilityCheck(value) { activeBackend.method.setStabilityCheck(value) }

    readonly property int methodCores: activeBackend.method.cores
    function methodSetCores(value) { activeBackend.method.setCores(value) }
    readonly property int methodMemoryGb: activeBackend.method.memoryGb
    function methodSetMemoryGb(value) { activeBackend.method.setMemoryGb(value) }

    ////////////////////////////////////
    // Job (Run card of the Method page)
    ////////////////////////////////////
    readonly property string jobState: activeBackend.job.state
    readonly property string jobStateLabel: activeBackend.job.stateLabel
    readonly property bool jobRunning: activeBackend.job.running
    readonly property string jobMessage: activeBackend.job.message
    readonly property var jobStepStates: activeBackend.job.stepStates  // by calculation type
    readonly property string jobFolder: activeBackend.job.folder
    readonly property string jobInputPath: activeBackend.job.inputPath
    readonly property string jobOutputPath: activeBackend.job.outputPath
    // Whole output: cleared when a job starts, complete when it ends; `jobOutputAppended` in between.
    readonly property string jobOutput: activeBackend.job.output
    function jobRun() { activeBackend.job.run() }
    function jobStop() { activeBackend.job.stop() }

    ///////////////////////////////////
    // Summary page: results of the job
    ///////////////////////////////////
    readonly property bool resultsAvailable: activeBackend.results.available
    readonly property string resultsPlaceholder: activeBackend.results.placeholder
    readonly property var resultsTiles: activeBackend.results.tiles
    readonly property bool resultsHasOptimisation: activeBackend.results.hasOptimisation
    readonly property var resultsGeometryRows: activeBackend.results.geometryRows
    readonly property var resultsConvergenceRows: activeBackend.results.convergenceRows
    readonly property bool resultsHasFrequencies: activeBackend.results.hasFrequencies
    readonly property bool resultsHasIr: activeBackend.results.hasIr
    readonly property bool resultsHasRaman: activeBackend.results.hasRaman
    readonly property var resultsModes: activeBackend.results.modes

    /////////////////////////////////////////////
    // Assistant panel (toggled from the app bar)
    /////////////////////////////////////////////
    // The configured model, or the offline stub's name
    readonly property string assistantModelName: activeBackend.assistant.modelName
    // Whether turns go to the model (SDK installed, not offline, a credential found)
    readonly property bool assistantConfigured: activeBackend.assistant.configured
    // [{id, role: 'user' | 'assistant' | 'action' | 'notice' | 'error', text, ok, page}] in order
    readonly property var assistantMessages: activeBackend.assistant.messages
    readonly property int assistantMessageCount: activeBackend.assistant.messageCount
    // A turn is in progress: sending is refused until it ends
    readonly property bool assistantBusy: activeBackend.assistant.busy
    // 'Thinking' | 'Waiting for your confirmation' | 'Cancelling' | ''
    readonly property string assistantStatus: activeBackend.assistant.status
    // The answer being written, before it becomes a message
    readonly property string assistantStreamingText: activeBackend.assistant.streamingText
    // {id, title, detail: [lines], confirm} of the action waiting for the user; {} when none
    readonly property var assistantApproval: activeBackend.assistant.approval
    // Questions offered for the current page and job state
    readonly property var assistantSuggestions: activeBackend.assistant.suggestions
    readonly property string assistantUsageText: activeBackend.assistant.usageText
    // 'home' | 'project' | 'sample' | 'calculations' | 'method' | 'summary'
    function assistantSetPage(name) { activeBackend.assistant.setPage(name) }
    function assistantSend(text) { activeBackend.assistant.send(text) }
    // Stops the answer being written; the conversation stays, a running job is not stopped
    function assistantCancel() { activeBackend.assistant.cancel() }
    function assistantClear() { activeBackend.assistant.clear() }
    function assistantAnswerApproval(id, allowed) { activeBackend.assistant.answerApproval(id, allowed) }

    // Assistant settings (the settings dialog)
    readonly property string assistantSettingsModel: activeBackend.assistant.settings.model
    readonly property var assistantSettingsModelChoices: activeBackend.assistant.settings.modelChoices
    function assistantSettingsSetModel(value) { activeBackend.assistant.settings.setModel(value) }
    readonly property string assistantSettingsEffort: activeBackend.assistant.settings.effort
    readonly property var assistantSettingsEffortChoices: activeBackend.assistant.settings.effortChoices
    function assistantSettingsSetEffort(value) { activeBackend.assistant.settings.setEffort(value) }
    readonly property string assistantSettingsApprovalMode: activeBackend.assistant.settings.approvalMode
    readonly property var assistantSettingsApprovalModeChoices: activeBackend.assistant.settings.approvalModeChoices
    function assistantSettingsSetApprovalMode(value) { activeBackend.assistant.settings.setApprovalMode(value) }
    readonly property bool assistantSettingsSendOutput: activeBackend.assistant.settings.sendOutput
    function assistantSettingsSetSendOutput(value) { activeBackend.assistant.settings.setSendOutput(value) }
    readonly property bool assistantSettingsSendResults: activeBackend.assistant.settings.sendResults
    function assistantSettingsSetSendResults(value) { activeBackend.assistant.settings.setSendResults(value) }
    readonly property bool assistantSettingsOffline: activeBackend.assistant.settings.offline
    function assistantSettingsSetOffline(value) { activeBackend.assistant.settings.setOffline(value) }
    // The key itself is never readable from QML
    readonly property bool assistantSettingsHasKey: activeBackend.assistant.settings.hasKey
    // 'assistant settings' | 'environment variable' | 'Anthropic CLI profile' | '' (none)
    readonly property string assistantSettingsKeySource: activeBackend.assistant.settings.keySource
    // 'session' | 'keyring' | 'settings' for a key entered here
    readonly property string assistantSettingsKeyStorage: activeBackend.assistant.settings.keyStorage
    readonly property bool assistantSettingsSecureStoreAvailable: activeBackend.assistant.settings.secureStoreAvailable
    readonly property bool assistantSettingsSdkAvailable: activeBackend.assistant.settings.sdkAvailable
    function assistantSettingsSetKey(key, remember) { activeBackend.assistant.settings.setKey(key, remember) }
    function assistantSettingsClearKey() { activeBackend.assistant.settings.clearKey() }
    // Answer comes as assistantSettingsVerified(message)
    function assistantSettingsVerify() { activeBackend.assistant.settings.verify() }

    // Signals forwarded from the backend
    signal projectSaved(string path)
    signal projectSaveError(string message)
    signal projectLoadError(string message)
    signal sampleLoadError(string message)
    signal sampleStructureLoaded()
    signal jobOutputAppended(string text)
    signal assistantReplied()
    signal assistantNavigateRequested(string page)
    signal assistantSettingsVerified(string message)

    Component.onCompleted: {
        activeBackend.project.projectSaved.connect(projectSaved)
        activeBackend.project.projectSaveError.connect(projectSaveError)
        activeBackend.project.projectLoadError.connect(projectLoadError)
        activeBackend.sample.loadError.connect(sampleLoadError)
        activeBackend.sample.structureLoaded.connect(sampleStructureLoaded)
        activeBackend.job.outputAppended.connect(jobOutputAppended)
        activeBackend.assistant.replied.connect(assistantReplied)
        activeBackend.assistant.navigateRequested.connect(assistantNavigateRequested)
        activeBackend.assistant.settings.verified.connect(assistantSettingsVerified)
    }

}
