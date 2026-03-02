import React from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";

import HomePage from "./pages/HomePage";
import DetailDatasetPage from "./pages/DatasetDetailPage";
import CreateDatasetTaskPage from "./pages/CreateDatasetTaskPage";
import ModelDetailPage from "./pages/ModelDetailPage";
import TrainModelPage from "./pages/TrainModelPage";
import ServeModelPage from "./pages/ServeModelPage";


function App() {
  return (
    <Router>
      <Routes>
        {/* main */}
        <Route path="/" element={<HomePage />} />

        {/* ================= DATASETS ================= */}
        <Route
          path="/datasets/:datasetId"
          element={<DetailDatasetPage />}
        />

        <Route
          path="/datasets/task/:resultId"
          element={<CreateDatasetTaskPage />}
        />

        {/* ================= MODELS ================= */}
        <Route
          path="/models/:modelId"
          element={<ModelDetailPage />}
        />

        <Route
          path="/models/:modelId/train/:resultId"
          element={<TrainModelPage />}
        />
        <Route path="/models/:modelId/serve" element={<ServeModelPage />} />

      </Routes>
    </Router>
  );
}

export default App;