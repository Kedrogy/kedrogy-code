import { BrowserRouter as Router, Routes, Route } from "react-router-dom";

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
      <Routes>
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
