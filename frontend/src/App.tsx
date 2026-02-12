import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AppProvider } from './store/AppContext';
import {
  SplashScreen,
  VegetableSelect,
  ConfigurationScreen,
  ProcessingScreen,
} from './pages';

function App() {
  return (
    <BrowserRouter>
      <AppProvider>
        <Routes>
          <Route path="/" element={<SplashScreen />} />
          <Route path="/select" element={<VegetableSelect />} />
          <Route path="/configure/:id" element={<ConfigurationScreen />} />
          <Route path="/processing" element={<ProcessingScreen />} />
        </Routes>
      </AppProvider>
    </BrowserRouter>
  );
}

export default App;
