/**
 * SPDX-FileCopyrightText: Copyright © 2020 The University of Texas at Austin
 * SPDX-FileContributor: Xinya Zhang <xinyazhang@utexas.edu>
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include <unistd.h>
#include <string>
#include <unordered_map>
#include <Eigen/Core>
#include <iostream>
#include <limits>
#include <igl/barycenter.h>
#include <igl/opengl/glfw/Viewer.h>
#include <igl/jet.h>
#include <time.h>

#include <heatio/readheat.h>
#include <advplyio/ply_write_vfc.h>
#include <tetio/readtet.h>

using Viewer = igl::opengl::glfw::Viewer;
using ViewerData = igl::opengl::ViewerData;
using MeshGL = igl::opengl::MeshGL;

using std::string;
using std::endl;
using std::cerr;
using std::fixed;
using std::vector;

void usage()
{
	cerr << "Options: -i <tetgen file prefix> -f <heat field data file> [-p <path file name> -r]" << endl
	     << "\t-r: enable auto range. The default range is 0-1" << endl;
}

class KeyDown {
private:
	Eigen::MatrixXd& V_;
	Eigen::MatrixXi& E_;
	Eigen::MatrixXi& P_;
	Eigen::MatrixXd B;
	vector<HeatFrame>& frames_;
	int frameid_ = 0;

	bool calibre_frameid()
	{
		int precalid = frameid_;
		frameid_ = std::max(frameid_, 0);
		frameid_ = std::min(int(frames_.size() - 1), frameid_);
		return precalid != frameid_;
	}

	vector<int> tetleft_;
	Eigen::MatrixXd V_temp_;
	Eigen::MatrixXi F_temp_;
	Eigen::VectorXd Z_temp_;
	std::unordered_map<int, int> vertidmap_; // Old vert id -> New vert id
	vector<int> vertback_;
	bool flush_viewer_ = false;
	vector<int> pathvertid_;
	vector<int> pathvertid_temp_;
	bool auto_range_ = false;

	vector<Eigen::Vector3d> pathvert_;
	Eigen::MatrixXd pathV_; // We need add another vertex to make a face for each segment.
	Eigen::MatrixXi pathF_;
public:
	KeyDown(
		Eigen::MatrixXd& V,
		Eigen::MatrixXi& E,
		Eigen::MatrixXi& P,
		vector<HeatFrame>& frames
		)
		: V_(V), E_(E), P_(P), frames_(frames)
	{
		igl::barycenter(V,P,B);
		frameid_ = 0;
		std::cerr << "KeyDown constructor was called " << endl;
		adjust_slice_plane(0.5);
	}

	void colorize_data(const Eigen::VectorXd& Z, Eigen::MatrixXd& C)
	{
		if (auto_range_)
			igl::jet(Z, true, C);
		else
			igl::jet(Z, 0.0, 1.0, C);
		for(auto vert : pathvertid_temp_) {
			C.row(vert) = Eigen::Vector3d(1.0, 1.0, 1.0);
		}
		for (auto i = vertback_.size(); i < Z.rows(); i++)
			C.row(i) = Eigen::Vector3d(1.0, 1.0, 1.0);
	}

	void save_frame()
	{
		time_t tnow = time(NULL);
		string now = ctime(&tnow);
		now = now.substr(0, now.size() - 1);
		Eigen::MatrixXd C;
		colorize_data(Z_temp_, C);
		string fn = "visheat-snapshot-at-"+now+"-frame-"+std::to_string(frameid_)+".ply";
		std::cerr << "Saving model to file " << fn;
		ply_write_vfc(fn,
				V_temp_,
				F_temp_,
				C);
		std::cerr << " done" << endl;
	}

	void set_auto_range(bool newvalue)
	{
		auto_range_ = newvalue;
	}

	void adjust_slice_plane(double t)
	{
		Eigen::VectorXd v = B.col(2).array() - B.col(2).minCoeff();
		v /= v.col(0).maxCoeff();

		Eigen::VectorXd vmark;
		vmark.setZero(v.size());
		tetleft_.clear();
		for (unsigned i = 0; i < v.size(); ++i) {
			if (v(i) < t) {
				tetleft_.emplace_back(i);
				for(int j = 0; j < 4; j++) {
					vmark(P_(i, j)) = 1;
				}
			}
		}
		vertidmap_.clear();
		vertback_.clear();
		int vertid = 0;
		for(unsigned i = 0; i < v.size(); i++) {
			if (vmark(i) > 0) {
				vertidmap_[i] = vertid; // forward mapping, old -> new
				vertback_.emplace_back(i); // back mapping, new -> old
				vertid++;
			}
		}
		V_temp_.resize(vertback_.size() + pathV_.rows(), 3);
		for(unsigned i = 0; i < vertback_.size(); i++) {
			V_temp_.row(i) = V_.row(vertback_[i]);
		}
		if (pathV_.rows() > 0)
			V_temp_.block(vertback_.size(), 0, pathV_.rows(), 3)
				= pathV_;

		F_temp_.resize(tetleft_.size()*4 + pathF_.rows(), 3);
		// Put old vert id to F_temp_
		for (unsigned i = 0; i < tetleft_.size(); ++i) {
			Eigen::VectorXi tet = P_.row(tetleft_[i]);
			F_temp_.row(i*4+0) << tet(0), tet(1), tet(3);
			F_temp_.row(i*4+1) << tet(0), tet(2), tet(1);
			F_temp_.row(i*4+2) << tet(3), tet(2), tet(0);
			F_temp_.row(i*4+3) << tet(1), tet(2), tet(3);
		}
		if (pathF_.rows() > 0)
			F_temp_.block(tetleft_.size() * 4, 0, pathF_.rows(), 3)
				= pathF_.array() + vertback_.size();
		// Translate to new vert id
		for(unsigned j = 0; j < tetleft_.size()*4; j++)
			for(unsigned k = 0; k < 3; k++)
				F_temp_(j,k) = vertidmap_[F_temp_(j,k)];
		Z_temp_.resize(V_temp_.rows());

		pathvertid_temp_.clear();
		for (int vert : pathvertid_) {
			auto iter = vertidmap_.find(vert);
			if (iter == vertidmap_.end())
				continue ;
			pathvertid_temp_.emplace_back(iter->second);
		}

		flush_viewer_ = true;
	}

	void update_frame(Viewer& viewer)
	{
		Eigen::VectorXd& FV(frames_[frameid_].hvec);
#if 0
		for (unsigned i = 0; i < tetleft_.size(); ++i) {
#if 0
			Z_temp_(i*4+0) = FV(P_(tetleft_[i],0));
			Z_temp_(i*4+1) = FV(P_(tetleft_[i],1));
			Z_temp_(i*4+2) = FV(P_(tetleft_[i],2));
			Z_temp_(i*4+3) = FV(P_(tetleft_[i],3));
#else
			Z_temp_(i*4+0) = V_(P_(tetleft_[i],0), 2);
			Z_temp_(i*4+1) = V_(P_(tetleft_[i],1), 2);
			Z_temp_(i*4+2) = V_(P_(tetleft_[i],2), 2);
			Z_temp_(i*4+3) = V_(P_(tetleft_[i],3), 2);
#endif
		}
#else
		for (unsigned i = 0; i < vertback_.size(); ++i) {
			Z_temp_(i) = FV(vertback_[i]);
		}
#endif
		if (flush_viewer_) {
			viewer.data().clear();
			viewer.data().set_mesh(V_temp_, F_temp_);
			flush_viewer_ = false;
		}
		viewer.data().set_face_based(false);
		viewer.data().V_material_diffuse.resize(vertback_.size(), 3);
		
		colorize_data(Z_temp_, viewer.data().V_material_diffuse);
		viewer.data().V_material_ambient = 0.1 * viewer.data().V_material_diffuse;
		constexpr double grey = 0.3;
		viewer.data().V_material_specular = grey+0.1*(viewer.data().V_material_diffuse.array()-grey);
		viewer.data().dirty |= MeshGL::DIRTY_DIFFUSE;
		// The code above replaces viewer.data.set_colors(C);
		// to calculate the result in-place
	}

	bool operator()(Viewer& viewer, unsigned char key, int modifier)
	{
		using namespace std;
		using namespace Eigen;
		bool redraw = false;

		if (toupper(key) == 'K') {
			frameid_ -= frames_.size()/10;
			redraw = true;
		} else if (toupper(key) == 'J') {
			frameid_ += frames_.size()/10;
			redraw = true;
		} 
		calibre_frameid();

		std::cerr << "Frame ID: " << frameid_
			<< "\tStepping: " << frames_.size() / 10
			<< "\tKey: " << key << " was pressed "
			<< endl;

		if (key >= '1' && key <= '9') {
			double t = double((key - '1')+1) / 8.0;
			redraw = true;
			adjust_slice_plane(t);
			std::cerr << "Tet left: " << tetleft_.size() << endl;
		}
		if (redraw)
			update_frame(viewer);

		if (toupper(key) == 'S') {
			save_frame();
			viewer.core.is_animating = false;
		}

		return false;
	}

	bool next_frame() 
	{
		frameid_++;
		std::cerr << frameid_ << ' ';
		return calibre_frameid();
	}

	void load_path(const string& path_file)
	{
		if (path_file.empty())
			return;
		std::ifstream fin(path_file);
		if (!fin.is_open())
			return;
		double x,y,z,tmp;
		int vert;
		bool extra_path = false;
		while (true) {
			while (fin.peek() == '#' && !fin.eof())
				fin.ignore(std::numeric_limits<std::streamsize>::max(), '\n');
			if (fin.eof())
				break;
			fin >> x >> y >> z >> vert >> tmp;
			
			std::cerr << x << ' ' << y << ' ' << z << ' ' << vert << ' ' << tmp << endl;
			if (!fin.eof()) {
				if (vert >= 0)
					pathvertid_.emplace_back(vert);
				else
					extra_path = true;
				pathvert_.emplace_back(x, y, z);
			} else {
				break;
			}
			fin.ignore(std::numeric_limits<std::streamsize>::max(), '\n');
		}
		std::cerr << "Loading done" << endl;
		if (extra_path)
			build_path_geo();
	}

	void build_path_geo()
	{
		auto npathvert = pathvert_.size();
		pathV_.resize(3 * (npathvert - 1), 3);
		pathF_.resize(npathvert - 1, 3);
		Eigen::Vector3d prev_vert = pathvert_.front();
		for (size_t i = 1; i < npathvert; i++) {
			Eigen::Vector3d vert = pathvert_[i];
			size_t vstart = 3 * (i - 1);
			pathV_.row(vstart) = prev_vert;
			pathV_.row(vstart + 1) = vert;
			vert(2) += 1e-2;
			pathV_.row(vstart + 2) = vert;
			pathF_(i - 1, 0) = vstart;
			pathF_(i - 1, 1) = vstart + 1;
			pathF_(i - 1, 2) = vstart + 2;
			prev_vert = vert;
		}
		std::cerr << "path building done" << endl;
	}
};

int main(int argc, char* argv[])
{
	int opt;
	bool auto_range = false;
	string iprefix, ffn, pfn;
	while ((opt = getopt(argc, argv, "i:f:p:r")) != -1) {
		switch (opt) {
			case 'i': 
				iprefix = optarg;
				break;
			case 'f':
				ffn = optarg;
				break;
			case 'p':
				pfn = optarg;
				break;
			case 'r':
				auto_range = true;
				break;
			default:
				std::cerr << "Unrecognized option: " << optarg << endl;
				usage();
				return -1;
		}
	}
	if (iprefix.empty() || ffn.empty()) {
		std::cerr << "Missing input file" << endl;
		usage();
		return -1;
	}

	Eigen::MatrixXd V;
	Eigen::MatrixXi E;
	Eigen::MatrixXi P;
	Eigen::VectorXi EBM;
	vector<HeatFrame> frames;
	vector<double> times;
	try {
		readtet(iprefix, V, E, P, &EBM);

		std::ifstream fin(ffn);
		HeatReader hreader(fin);
		while (true) {
			HeatFrame frame;
			if (!hreader.read_frame(frame))
				break;
			frames.emplace_back(std::move(frame));
			frames.back().hvec.conservativeResize(V.rows()); // Trim hidden nodes.
		}
	} catch (std::runtime_error& e) {
		std::cerr << e.what() << std::endl;
		return -1;
	}

	Viewer viewer;
	KeyDown kd(V,E,P, frames);
	kd.load_path(pfn);
	kd.set_auto_range(auto_range);
	viewer.callback_key_pressed = [&kd](Viewer& viewer, unsigned char key, int modifier) -> bool { return kd.operator()(viewer, key, modifier); } ;
	viewer.callback_pre_draw = [&kd](Viewer& viewer) -> bool
	{
		if (viewer.core.is_animating) {
			if (!kd.next_frame())
				kd.update_frame(viewer);
		}
		return false;
	};
	viewer.core.is_animating = true;
	viewer.core.animation_max_fps = 5.;
	viewer.launch();

	return 0;
}
