import { BrowserRouter as Router, Routes, Route } from "react-router-dom";

import { LanguageSwitcher } from "./components/LanguageSwitcher";

import CleanupPage from "./pages/CleanupPage";
import RetainedAnnotationsPage from "./pages/RetainedAnnotationsPage";
import HomePage from "./pages/HomePage";
import DatasetDetailPage from "./pages/DatasetDetailPage";
import CreateDatasetTaskPage from "./pages/CreateDatasetTaskPage";
import ModelDetailPage from "./pages/ModelDetailPage";
import TrainModelPage from "./pages/TrainModelPage";
import ServeModelPage from "./pages/ServeModelPage";
import DeleteModelPage from "./pages/DeleteModelPage";

function App() {
  return (
    <Router>
      <LanguageSwitcher />
      <Routes>
        <Route path="/cleanup/:target/:id/:action" element={<CleanupPage />} />
        <Route path="/operations/delete/:resultId" element={<DeleteModelPage />} />
        <Route path="/retained-annotations" element={<RetainedAnnotationsPage />} />
        {/* main */}
        <Route path="/" element={<HomePage />} />

        {/* ================= DATASETS ================= */}
        <Route path="/datasets/:datasetId" element={<DatasetDetailPage />} />
        <Route path="/datasets/task/:resultId" element={<CreateDatasetTaskPage />} />

        {/* ================= MODELS ================= */}
        <Route path="/models/:modelId" element={<ModelDetailPage />} />
        <Route path="/models/:modelId/train/:resultId" element={<TrainModelPage />} />
        <Route path="/models/:modelId/serve/:resultId" element={<ServeModelPage />} />
        <Route path="/models/:modelId/delete/:resultId" element={<DeleteModelPage />} />
      </Routes>
    </Router>
  );
}

export default App;
