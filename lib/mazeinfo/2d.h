/**
 * SPDX-FileCopyrightText: Copyright © 2020 The University of Texas at Austin
 * SPDX-FileContributor: Xinya Zhang <xinyazhang@utexas.edu>
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef MAZEINFO_2D_H
#define MAZEINFO_2D_H

#include <Eigen/Core>
#include <boost/range/irange.hpp>
#include <vector>
#include <ostream>

typedef Eigen::Vector2d MazeVert;
typedef std::vector<MazeVert, Eigen::aligned_allocator<MazeVert> > MazeVertArray;

class MazeSegment {
public:
	MazeVert v0, v1;
};

class MazeBoundary {
public:
	MazeBoundary(std::istream&);

	MazeSegment& get_prim(int idx); // Get #idx primitive
	MazeVert get_center() const;
	auto irange() { return boost::irange(0, (int)segs_.size()); }

	void get_bbox(MazeVert& minV, MazeVert& maxV) const;
	void merge_bbox(MazeVert& minV, MazeVert& maxV) const;

	void writePLY(std::ostream&, Eigen::Vector3d color = Eigen::Vector3d(1.0, 1.0, 1.0));
	void convertVF(Eigen::MatrixXd& V, Eigen::MatrixXi& F);
private:
	std::vector<MazeSegment> segs_;
	MazeVert center_;
};


#endif
