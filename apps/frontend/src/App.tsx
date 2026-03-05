import { BrowserRouter, Routes, Route } from "react-router-dom"
import Layout from "./Layout"
import Dashboard from "./pages/Dashboard"
import Studio from "./pages/Studio"
import LocationDetail from "./pages/LocationDetail"

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="studio" element={<Studio />} />
          <Route path="location/:locId" element={<LocationDetail />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
