pragma Singleton

import QtQuick

import Backends as Backends

// Wrapper to the Python backend API, exposing its properties and methods to the QML GUI.
// - In GUI code, backend properties and methods MUST be accessed through this object.
// - Flat structure: the backend part is encoded in the name (projectName = backend.project.name).
// - Writable properties get a setter function; assigning them from QML would break the binding.

QtObject {

    readonly property var activeBackend: Backends.PyBackend

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
    function projectReset() { activeBackend.project.reset() }

    //////////////
    // Sample page
    //////////////
    readonly property string sampleName: activeBackend.sample.name
    readonly property string sampleSource: activeBackend.sample.source
    readonly property string sampleFormula: activeBackend.sample.formula
    readonly property string sampleSummary: activeBackend.sample.summary
    readonly property int sampleAtomCount: activeBackend.sample.atomCount
    readonly property bool samplePeriodic: activeBackend.sample.periodic
    readonly property int sampleCharge: activeBackend.sample.charge
    readonly property int sampleMultiplicity: activeBackend.sample.multiplicity
    readonly property var sampleAtoms: activeBackend.sample.atoms
    readonly property var sampleBonds: activeBackend.sample.bonds
    readonly property int sampleFixedCount: activeBackend.sample.fixedCount
    function sampleSetAtomFixed(index, value) { activeBackend.sample.setAtomFixed(index, value) }

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
    readonly property string methodEngineName: activeBackend.method.engineName
    readonly property bool methodEngineFound: activeBackend.method.engineFound
    readonly property string methodEngineVersion: activeBackend.method.engineVersion
    readonly property string methodEnginePath: activeBackend.method.enginePath
    readonly property string methodEngineCardText: activeBackend.method.engineCardText
    function methodRedetect() { activeBackend.method.redetect() }
    function methodSetEnginePath(value) { activeBackend.method.setEnginePath(value) }

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

    readonly property string methodScfConvergence: activeBackend.method.scfConvergence
    readonly property var methodScfConvergenceChoices: activeBackend.method.scfConvergenceChoices
    function methodSetScfConvergence(value) { activeBackend.method.setScfConvergence(value) }
    readonly property int methodScfMaxIterations: activeBackend.method.scfMaxIterations
    function methodSetScfMaxIterations(value) { activeBackend.method.setScfMaxIterations(value) }
    readonly property string methodIntegrationGrid: activeBackend.method.integrationGrid
    readonly property var methodIntegrationGridChoices: activeBackend.method.integrationGridChoices
    function methodSetIntegrationGrid(value) { activeBackend.method.setIntegrationGrid(value) }
    readonly property bool methodStabilityCheck: activeBackend.method.stabilityCheck
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
    readonly property string jobFolder: activeBackend.job.folder
    readonly property string jobInputPath: activeBackend.job.inputPath
    readonly property string jobOutputPath: activeBackend.job.outputPath
    // Whole output: cleared when a job starts, complete when it ends; `jobOutputAppended` in between.
    readonly property string jobOutput: activeBackend.job.output
    function jobRun() { activeBackend.job.run() }
    function jobStop() { activeBackend.job.stop() }

    // Signals forwarded from the backend
    signal projectSaved(string path)
    signal projectSaveError(string message)
    signal projectLoadError(string message)
    signal jobOutputAppended(string text)

    Component.onCompleted: {
        activeBackend.project.projectSaved.connect(projectSaved)
        activeBackend.project.projectSaveError.connect(projectSaveError)
        activeBackend.project.projectLoadError.connect(projectLoadError)
        activeBackend.job.outputAppended.connect(jobOutputAppended)
    }

}
