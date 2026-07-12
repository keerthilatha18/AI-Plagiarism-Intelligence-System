import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login.jsx'
import AssignmentList from './pages/AssignmentList.jsx'
import SubmissionList from './pages/SubmissionList.jsx'
import SubmissionDetail from './pages/SubmissionDetail.jsx'
import InstructorBaseline from './pages/InstructorBaseline.jsx'

function RequireAuth({ children }) {
  const instructor = localStorage.getItem('instructor_id')
  return instructor ? children : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <AssignmentList />
            </RequireAuth>
          }
        />
        <Route
          path="/assignments/:assignmentId/submissions"
          element={
            <RequireAuth>
              <SubmissionList />
            </RequireAuth>
          }
        />
        <Route
          path="/submissions/:submissionId"
          element={
            <RequireAuth>
              <SubmissionDetail />
            </RequireAuth>
          }
        />
        <Route
          path="/instructors/:instructorId/baseline"
          element={
            <RequireAuth>
              <InstructorBaseline />
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
